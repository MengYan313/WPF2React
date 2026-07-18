"""TypeScript 编译与页面调用测试的确定性进程执行器。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .models import (
    CallEdgeSpec,
    CallEvaluationResult,
    CallEvaluationStatus,
    CommandSpec,
    CompileResult,
    CompileStatus,
    ProcessEvidence,
)


_OUTPUT_TAIL_LIMIT = 4000


def _tail(value: str) -> str:
    return value[-_OUTPUT_TAIL_LIMIT:]


def _expand_command(command: list[str], values: dict[str, str]) -> list[str]:
    return [part.format_map(values) for part in command]


def _run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> ProcessEvidence:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    return ProcessEvidence(
        command=command,
        return_code=completed.returncode,
        duration_ms=round((time.monotonic() - started) * 1000),
        stdout_tail=_tail(completed.stdout),
        stderr_tail=_tail(completed.stderr),
    )


class TypeScriptCompileRunner:
    """按目标入口编译并缓存结果，不允许隐式下载 TypeScript。"""

    def __init__(self, target_root: Path, config: CommandSpec) -> None:
        self.target_root = target_root.resolve()
        self.config = config
        self._cache: dict[Path, CompileResult] = {}

    def compile(self, entry_file: Path) -> CompileResult:
        entry_file = entry_file.resolve()
        if entry_file in self._cache:
            return self._cache[entry_file]

        if not self._is_inside_target(entry_file) or not entry_file.is_file():
            result = CompileResult(
                entry_file=str(entry_file),
                status=CompileStatus.EVALUATOR_ERROR,
                error="编译入口不存在或位于 target_root 之外",
            )
            self._cache[entry_file] = result
            return result

        try:
            if self.config.command:
                result = self._compile_with_configured_command(entry_file)
            else:
                result = self._compile_with_local_tsc(entry_file)
        except subprocess.TimeoutExpired as exc:
            result = CompileResult(
                entry_file=str(entry_file.relative_to(self.target_root)),
                status=CompileStatus.EVALUATOR_ERROR,
                error=f"编译命令超过 {exc.timeout} 秒",
            )
        except (OSError, KeyError, ValueError) as exc:
            result = CompileResult(
                entry_file=str(entry_file.relative_to(self.target_root)),
                status=CompileStatus.EVALUATOR_ERROR,
                error=f"编译器执行失败: {exc}",
            )

        self._cache[entry_file] = result
        return result

    def _compile_with_configured_command(self, entry_file: Path) -> CompileResult:
        tsconfig = self.target_root / "tsconfig.json"
        command = _expand_command(
            self.config.command,
            {
                "entry": str(entry_file),
                "target_root": str(self.target_root),
                "tsconfig": str(tsconfig),
            },
        )
        evidence = _run_process(
            command,
            cwd=self.target_root,
            timeout_seconds=self.config.timeout_seconds,
        )
        return CompileResult(
            entry_file=str(entry_file.relative_to(self.target_root)),
            status=(
                CompileStatus.PASSED
                if evidence.return_code == 0
                else CompileStatus.FAILED
            ),
            evidence=evidence,
        )

    def _compile_with_local_tsc(self, entry_file: Path) -> CompileResult:
        tsconfig = self.target_root / "tsconfig.json"
        if not tsconfig.is_file():
            return CompileResult(
                entry_file=str(entry_file.relative_to(self.target_root)),
                status=CompileStatus.EVALUATOR_ERROR,
                error="target_root 缺少 tsconfig.json，且 manifest 未配置 compiler.command",
            )

        local_tsc = self.target_root / "node_modules" / ".bin" / "tsc"
        tsc = str(local_tsc) if local_tsc.is_file() else shutil.which("tsc")
        if not tsc:
            return CompileResult(
                entry_file=str(entry_file.relative_to(self.target_root)),
                status=CompileStatus.EVALUATOR_ERROR,
                error="未找到本地 node_modules/.bin/tsc 或 PATH 中的 tsc；评测器不会隐式下载",
            )

        with tempfile.TemporaryDirectory(prefix="wpf2react-tsc-") as temp_dir:
            eval_config = Path(temp_dir) / "tsconfig.eval.json"
            eval_config.write_text(
                json.dumps(
                    {
                        "extends": str(tsconfig.resolve()),
                        "compilerOptions": {
                            "noEmit": True,
                            "incremental": False,
                            "composite": False,
                        },
                        "files": [str(entry_file)],
                        "include": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            command = [tsc, "--pretty", "false", "-p", str(eval_config)]
            evidence = _run_process(
                command,
                cwd=self.target_root,
                timeout_seconds=self.config.timeout_seconds,
            )

        return CompileResult(
            entry_file=str(entry_file.relative_to(self.target_root)),
            status=(
                CompileStatus.PASSED
                if evidence.return_code == 0
                else CompileStatus.FAILED
            ),
            evidence=evidence,
        )

    def _is_inside_target(self, path: Path) -> bool:
        try:
            path.relative_to(self.target_root)
            return True
        except ValueError:
            return False


class CallTestRunner:
    """为冻结的页面调用边执行预注册测试代码。"""

    def __init__(self, target_root: Path, config: CommandSpec) -> None:
        self.target_root = target_root.resolve()
        self.config = config

    def is_configured(self, edge: CallEdgeSpec) -> bool:
        return bool((edge.test_command or self.config.command) and edge.test_file)

    def run(self, edge: CallEdgeSpec) -> CallEvaluationResult:
        command_template = edge.test_command or self.config.command
        if not self.is_configured(edge):
            return CallEvaluationResult(
                edge_id=edge.edge_id,
                source_page=edge.source_page,
                target_page=edge.target_page,
                status=CallEvaluationStatus.TEST_NOT_CONFIGURED,
                error="调用边缺少 test_file 或测试命令",
            )

        test_file = (self.target_root / edge.test_file).resolve()
        try:
            test_file.relative_to(self.target_root)
        except ValueError:
            return self._evaluator_error(edge, "test_file 位于 target_root 之外")
        if not test_file.is_file():
            return self._evaluator_error(edge, f"测试文件不存在: {edge.test_file}")

        try:
            command = _expand_command(
                command_template,
                {
                    "edge_id": edge.edge_id,
                    "source_page": edge.source_page,
                    "target_page": edge.target_page,
                    "target_root": str(self.target_root),
                    "test_file": str(test_file),
                },
            )
            evidence = _run_process(
                command,
                cwd=self.target_root,
                timeout_seconds=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return self._evaluator_error(
                edge, f"调用测试超过 {exc.timeout} 秒"
            )
        except (OSError, KeyError, ValueError) as exc:
            return self._evaluator_error(edge, f"调用测试执行失败: {exc}")

        return CallEvaluationResult(
            edge_id=edge.edge_id,
            source_page=edge.source_page,
            target_page=edge.target_page,
            status=(
                CallEvaluationStatus.TEST_PASSED
                if evidence.return_code == 0
                else CallEvaluationStatus.TEST_FAILED
            ),
            evidence=evidence,
        )

    @staticmethod
    def _evaluator_error(edge: CallEdgeSpec, message: str) -> CallEvaluationResult:
        return CallEvaluationResult(
            edge_id=edge.edge_id,
            source_page=edge.source_page,
            target_page=edge.target_page,
            status=CallEvaluationStatus.EVALUATOR_ERROR,
            error=message,
        )
