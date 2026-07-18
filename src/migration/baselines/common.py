"""基线共享的目录、目标骨架、资源复制与审计辅助函数。"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


METHOD_RULETRANS = "RuleTrans-MUI"
METHOD_LLM_DIRECT = "LLM-Direct-Budget"
METHOD_NO_RAG = "MigraUI-NoRAG"
METHOD_IDS = (METHOD_RULETRANS, METHOD_LLM_DIRECT, METHOD_NO_RAG)

_ALLOWED_GENERATED_SUFFIXES = {".ts", ".tsx", ".css"}
_BINARY_ASSET_SUFFIXES = {
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
}


@dataclass(frozen=True)
class BaselineRunPaths:
    """一个方法—运行—项目组合的隔离目录。"""

    method_id: str
    run_id: str
    project_id: str
    source_root: Path
    result_root: Path
    artifact_root: Path

    @classmethod
    def build(
        cls,
        method_id: str,
        run_id: str,
        project_id: str,
        *,
        source_base_dir: str | Path = "repos",
        result_base_dir: str | Path = "results/baselines",
        artifact_base_dir: str | Path = "outputs/baselines",
    ) -> "BaselineRunPaths":
        if method_id not in METHOD_IDS:
            raise ValueError(f"未知 baseline: {method_id}")
        for label, value in (("run_id", run_id), ("project_id", project_id)):
            if not value or value in {".", ".."} or "/" in value or "\\" in value:
                raise ValueError(f"{label} 必须是非空的单段目录名")

        source_base = Path(source_base_dir).resolve()
        source_root = (source_base / project_id).resolve()
        try:
            source_root.relative_to(source_base)
        except ValueError as exc:
            raise ValueError("项目路径超出 repos 范围") from exc
        if not source_root.is_dir():
            raise FileNotFoundError(f"WPF 项目不存在: {source_root}")

        return cls(
            method_id=method_id,
            run_id=run_id,
            project_id=project_id,
            source_root=source_root,
            result_root=(Path(result_base_dir) / method_id / run_id / project_id).resolve(),
            artifact_root=(
                Path(artifact_base_dir) / method_id / run_id / project_id
            ).resolve(),
        )

    def prepare(self) -> None:
        """创建全新运行目录；不覆盖已经存在的实验证据。"""
        for path in (self.result_root, self.artifact_root):
            if path.exists() and any(path.iterdir()):
                raise FileExistsError(
                    f"运行目录已存在且非空: {path}；请使用新的 --run-id"
                )
            path.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def estimate_tokens(text: str, model: str | None = None) -> int:
    """不下载编码表的保守离线 token 估算。

    CJK 字符按一个 token、其余字符按四分之一个 token 计；UTF-8 字节数
    除以四作为另一条下界。正式成本指标仍以 provider usage 为准。
    """
    del model  # 估算器有意与在线模型注册表解耦，保证离线可复现。
    cjk_count = sum(
        "\u3400" <= character <= "\u9fff" or "\uf900" <= character <= "\ufaff"
        for character in text
    )
    non_cjk_count = len(text) - cjk_count
    character_estimate = cjk_count + (non_cjk_count + 3) // 4
    byte_estimate = (len(text.encode("utf-8")) + 3) // 4
    return max(1, character_estimate, byte_estimate)


def safe_generated_path(result_root: Path, relative_path: str) -> Path:
    """只允许模型在本次结果目录写入源码/样式文件。"""
    normalized = relative_path.strip().replace("\\", "/")
    candidate_rel = Path(normalized)
    if (
        not normalized
        or candidate_rel.is_absolute()
        or ".." in candidate_rel.parts
        or candidate_rel.suffix.lower() not in _ALLOWED_GENERATED_SUFFIXES
        or "node_modules" in candidate_rel.parts
    ):
        raise ValueError(f"模型返回了不允许的目标路径: {relative_path!r}")
    candidate = (result_root / candidate_rel).resolve()
    try:
        candidate.relative_to(result_root.resolve())
    except ValueError as exc:
        raise ValueError(f"目标路径超出结果目录: {relative_path!r}") from exc
    return candidate


def write_generated_files(
    result_root: Path,
    files: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """原子式预检后写入模型生成文件，返回不含源码正文的审计记录。"""
    validated: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("files 中每一项必须是 JSON object")
        relative_path = str(item.get("path", ""))
        content = str(item.get("content", ""))
        if not content.strip():
            raise ValueError(f"模型返回了空文件: {relative_path!r}")
        target = safe_generated_path(result_root, relative_path)
        if target in seen:
            raise ValueError(f"模型在同一响应中重复返回文件: {relative_path}")
        seen.add(target)
        validated.append((target, content))
    if not validated:
        raise ValueError("模型响应没有可写入的源码文件")

    written: list[dict[str, Any]] = []
    for target, content in validated:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(
            {
                "path": str(target.relative_to(result_root)),
                "bytes": len(content.encode("utf-8")),
                "sha256": sha256_text(content),
            }
        )
    return written


def create_target_skeleton(result_root: Path) -> list[str]:
    """写入所有方法共享、且不含目标页面实现的空白 React 工程骨架。"""
    package = {
        "name": "wpf2react-baseline-target",
        "private": True,
        "version": "0.0.0",
        "type": "module",
        "scripts": {
            "build": "tsc --noEmit && vite build",
            "test": "vitest run",
        },
        "dependencies": {
            "@emotion/react": "11.11.4",
            "@emotion/styled": "11.11.5",
            "@mui/icons-material": "5.18.0",
            "@mui/material": "5.18.0",
            "react": "18.2.0",
            "react-dom": "18.2.0",
            "react-router-dom": "6.28.0",
        },
        "devDependencies": {
            "@types/react": "18.3.12",
            "@types/react-dom": "18.3.1",
            "@vitejs/plugin-react": "4.3.4",
            "typescript": "5.9.3",
            "vite": "5.4.21",
            "vitest": "2.1.8",
        },
    }
    files = {
        "package.json": json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        "tsconfig.json": json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "useDefineForClassFields": True,
                    "lib": ["ES2022", "DOM", "DOM.Iterable"],
                    "allowJs": False,
                    "skipLibCheck": True,
                    "esModuleInterop": True,
                    "allowSyntheticDefaultImports": True,
                    "strict": True,
                    "forceConsistentCasingInFileNames": True,
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "noEmit": True,
                    "jsx": "react-jsx",
                },
                "include": ["*.ts", "*.tsx", "src/**/*.ts", "src/**/*.tsx"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "vite.config.ts": (
            "import { defineConfig } from 'vite';\n"
            "import react from '@vitejs/plugin-react';\n\n"
            "export default defineConfig({ plugins: [react()] });\n"
        ),
        "index.html": (
            '<!doctype html><html><head><meta charset="UTF-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
            "<title>WPF2React Baseline</title></head><body>"
            '<div id="root"></div><script type="module" src="/main.tsx"></script>'
            "</body></html>\n"
        ),
        "main.tsx": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom/client';\n"
            "import { App } from './App';\n\n"
            "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
            "  <React.StrictMode><App /></React.StrictMode>,\n"
            ");\n"
        ),
        "App.tsx": (
            "export function App() {\n"
            "  return <div data-empty-target-shell />;\n"
            "}\n\n"
            "export default App;\n"
        ),
    }
    written: list[str] = []
    for relative, content in files.items():
        target = result_root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(relative)
    return written


def copy_binary_assets(source_root: Path, result_root: Path) -> list[dict[str, Any]]:
    """按原相对路径复制二进制资源；不生成或修复代码引用。"""
    records: list[dict[str, Any]] = []
    public_root = result_root / "public"
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in _BINARY_ASSET_SUFFIXES:
            continue
        relative = source.relative_to(source_root)
        target = public_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append(
            {
                "source": str(relative),
                "target": str(target.relative_to(result_root)),
                "sha256": sha256_file(target),
            }
        )
    return records


def copy_parser_outputs(
    project_id: str,
    artifact_root: Path,
    *,
    parser_output_base_dir: str | Path = "outputs",
) -> Path:
    """为 MigraUI 变体复制相同阶段1产物，隔离后续中间文件。"""
    source = Path(parser_output_base_dir).resolve() / project_id
    if not source.is_dir():
        raise FileNotFoundError(
            f"Parser 产物不存在: {source}；请先运行 python -m src.parser {project_id}"
        )
    isolated_base = artifact_root / "parser"
    target = isolated_base / project_id
    if target.exists():
        raise FileExistsError(f"隔离 Parser 目录已存在: {target}")
    target.mkdir(parents=True, exist_ok=False)
    copied_any = False
    for directory_name in ("cs", "xaml", "dependency"):
        source_directory = source / directory_name
        if not source_directory.is_dir():
            continue
        shutil.copytree(source_directory, target / directory_name)
        copied_any = True
    if not copied_any:
        raise FileNotFoundError(f"Parser 产物目录不完整: {source}")
    return isolated_base
