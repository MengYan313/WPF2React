"""比较两次阶段一全量运行的语义产物，验证文件集合与内容确定性。"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import write_json


DEFAULT_FIRST = Path("outputs/parser-completeness/after-run-1")
DEFAULT_SECOND = Path("outputs/parser-completeness/after-run-2")
DEFAULT_FIRST_REPORT = Path("results/parser-completeness/after-run-1")
DEFAULT_SECOND_REPORT = Path("results/parser-completeness/after-run-2")
DEFAULT_OUTPUT = Path("results/parser-completeness/determinism.json")
EXCLUDED_FILES = frozenset({"run_index.json", "run_summary.json"})


def _artifact_paths(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*.json"))
        if path.name not in EXCLUDED_FILES
    }


def _semantic_digest(
    path: Path,
    replacements: tuple[tuple[Path, bytes], ...],
) -> str:
    """归一化根路径后按原始字节哈希，保留键序、数组序和格式差异。"""
    encoded = path.read_bytes()
    for root, token in replacements:
        variants = {
            root.as_posix().encode("utf-8"),
            root.resolve().as_posix().encode("utf-8"),
            str(root).encode("utf-8"),
            str(root.resolve()).encode("utf-8"),
        }
        for variant in sorted(variants, key=len, reverse=True):
            if variant:
                encoded = encoded.replace(variant, token)
    return hashlib.sha256(encoded).hexdigest()


def compare_runs(first: Path, second: Path) -> dict[str, Any]:
    first_paths = _artifact_paths(first)
    second_paths = _artifact_paths(second)
    first_names = set(first_paths)
    second_names = set(second_paths)
    common = sorted(first_names & second_names)
    first_only = sorted(first_names - second_names)
    second_only = sorted(second_names - first_names)
    mismatches: list[dict[str, str]] = []
    matching = 0

    for relative in common:
        first_hash = _semantic_digest(
            first_paths[relative], ((first, b"<PARSE_ROOT>"),)
        )
        second_hash = _semantic_digest(
            second_paths[relative], ((second, b"<PARSE_ROOT>"),)
        )
        if first_hash == second_hash:
            matching += 1
        else:
            mismatches.append(
                {
                    "path": relative,
                    "first_sha256": first_hash,
                    "second_sha256": second_hash,
                }
            )

    deterministic = not first_only and not second_only and not mismatches
    return {
        "schema_version": 1,
        "comparison_scope": "parser-json-excluding-run-metadata",
        "normalization": ["parse_root_path"],
        "first_root": first.as_posix(),
        "second_root": second.as_posix(),
        "first_artifact_count": len(first_paths),
        "second_artifact_count": len(second_paths),
        "common_artifact_count": len(common),
        "matching_artifact_count": matching,
        "first_only": first_only,
        "second_only": second_only,
        "content_mismatches": mismatches,
        "deterministic": deterministic,
    }


def compare_reports(
    first: Path,
    second: Path,
    *,
    first_parse_root: Path,
    second_parse_root: Path,
) -> dict[str, Any]:
    def report_paths(root: Path) -> dict[str, Path]:
        return {
            path.relative_to(root).as_posix(): path
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.suffix in {".json", ".md"}
        }

    first_paths = report_paths(first)
    second_paths = report_paths(second)
    common = sorted(set(first_paths) & set(second_paths))
    first_only = sorted(set(first_paths) - set(second_paths))
    second_only = sorted(set(second_paths) - set(first_paths))
    mismatches: list[dict[str, str]] = []
    matching = 0
    for relative in common:
        first_hash = _semantic_digest(
            first_paths[relative],
            (
                (first, b"<REPORT_ROOT>"),
                (first_parse_root, b"<PARSE_ROOT>"),
            ),
        )
        second_hash = _semantic_digest(
            second_paths[relative],
            (
                (second, b"<REPORT_ROOT>"),
                (second_parse_root, b"<PARSE_ROOT>"),
            ),
        )
        if first_hash == second_hash:
            matching += 1
        else:
            mismatches.append(
                {
                    "path": relative,
                    "first_sha256": first_hash,
                    "second_sha256": second_hash,
                }
            )
    return {
        "first_report_root": first.as_posix(),
        "second_report_root": second.as_posix(),
        "first_file_count": len(first_paths),
        "second_file_count": len(second_paths),
        "common_file_count": len(common),
        "matching_file_count": matching,
        "first_only": first_only,
        "second_only": second_only,
        "content_mismatches": mismatches,
        "deterministic": not first_only and not second_only and not mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, default=DEFAULT_FIRST)
    parser.add_argument("--second", type=Path, default=DEFAULT_SECOND)
    parser.add_argument(
        "--first-report-root", type=Path, default=DEFAULT_FIRST_REPORT
    )
    parser.add_argument(
        "--second-report-root", type=Path, default=DEFAULT_SECOND_REPORT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    for label, root in (("第一次运行", args.first), ("第二次运行", args.second)):
        if not root.is_dir():
            parser.error(f"{label}目录不存在: {root}")
    for label, root in (
        ("第一次审计", args.first_report_root),
        ("第二次审计", args.second_report_root),
    ):
        if not root.is_dir():
            parser.error(f"{label}目录不存在: {root}")

    result = compare_runs(args.first, args.second)
    result["parser_artifacts_deterministic"] = result["deterministic"]
    result["audit_reports"] = compare_reports(
        args.first_report_root,
        args.second_report_root,
        first_parse_root=args.first,
        second_parse_root=args.second,
    )
    result["statistics_deterministic"] = result["audit_reports"][
        "deterministic"
    ]
    result["deterministic"] = bool(
        result["parser_artifacts_deterministic"]
        and result["statistics_deterministic"]
    )
    write_json(args.output, result)
    print(
        "确定性比较: "
        f"artifacts={result['common_artifact_count']}, "
        f"matching={result['matching_artifact_count']}, "
        f"mismatches={len(result['content_mismatches'])}, "
        f"reports={result['audit_reports']['matching_file_count']}/"
        f"{result['audit_reports']['common_file_count']}, "
        f"deterministic={result['deterministic']}"
    )
    print(f"比较报告: {args.output}")
    return 0 if result["deterministic"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
