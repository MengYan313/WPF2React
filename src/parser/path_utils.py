"""解析器输入路径发现与过滤辅助函数。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


IGNORED_SOURCE_DIRECTORIES = frozenset(
    {
        ".git",
        ".idea",
        ".vs",
        ".vscode",
        "bin",
        "generated files",
        "node_modules",
        "obj",
    }
)


def is_ignored_source_path(path: Path, project_root: Path) -> bool:
    """判断路径是否位于生成目录、工具目录或仓库范围之外。"""
    try:
        relative = path.relative_to(project_root)
        resolved = path.resolve()
        resolved.relative_to(project_root.resolve())
    except (OSError, ValueError):
        return True

    if path.is_symlink():
        return True

    return any(
        part.lower() in IGNORED_SOURCE_DIRECTORIES for part in relative.parts[:-1]
    )


def discover_project_files(project_root: Path, suffixes: Iterable[str]) -> list[Path]:
    """确定性发现项目文件，并排除生成目录及越界符号链接。"""
    project_root = Path(project_root)
    files: set[Path] = set()
    for suffix in suffixes:
        normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        for path in project_root.rglob(f"*{normalized_suffix}"):
            if (
                path.is_file()
                and not is_ignored_source_path(path, project_root)
            ):
                files.add(path)
    return sorted(files, key=lambda path: str(path.relative_to(project_root)))
