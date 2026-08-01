"""源码文件与页面的仓库相对路径标识契约。"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


class SourceIdentityError(ValueError):
    """解析产物不满足仓库相对路径标识契约。"""


def artifact_source_id(data: Mapping[str, Any], artifact: str | Path) -> str:
    """返回解析产物中的仓库相对源码 ID。"""
    try:
        return normalize_source_id(str(data.get("source_id", "")))
    except ValueError as exc:
        raise SourceIdentityError(f"解析产物 {artifact} 缺少有效 source_id") from exc


def normalize_source_id(value: str) -> str:
    """规范化并校验仓库相对 POSIX 路径标识。"""
    normalized = str(value).replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"无效的仓库相对路径标识: {value!r}")
    return path.as_posix()


def repository_relative_id(source_path: str | Path, repository_root: str | Path) -> str:
    """返回源码文件相对于仓库根目录的稳定 POSIX 路径。"""
    source = Path(source_path).resolve()
    root = Path(repository_root).resolve()
    try:
        relative = source.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"源码文件不在仓库根目录内: {source}") from exc
    return normalize_source_id(PurePosixPath(*relative.parts).as_posix())


def mirrored_json_path(output_root: str | Path, source_id: str) -> Path:
    """返回镜像源码目录结构的解析 JSON 路径。"""
    normalized = normalize_source_id(source_id)
    source = PurePosixPath(normalized)
    return Path(output_root).joinpath(*source.parts).with_name(f"{source.name}.json")


def control_json_path(dependency_root: str | Path, page_id: str) -> Path:
    """返回页面控件树的镜像输出路径。"""
    return mirrored_json_path(Path(dependency_root) / "controls", normalize_page_id(page_id))


def normalize_page_id(value: str) -> str:
    """校验页面 ID；页面以对应 XAML 的仓库相对路径为唯一标识。"""
    page_id = normalize_source_id(value)
    if not page_id.casefold().endswith(".xaml"):
        raise ValueError(f"页面 ID 必须以 .xaml 结尾: {value!r}")
    return page_id


def normalize_cs_id(value: str) -> str:
    """校验 C# 源码 ID；必须保留仓库相对路径与 .cs 扩展名。"""
    source_id = normalize_source_id(value)
    if not source_id.casefold().endswith(".cs"):
        raise ValueError(f"C# 源码 ID 必须以 .cs 结尾: {value!r}")
    return source_id


def page_id_from_cs_id(source_id: str) -> str:
    """把 code-behind 的源码 ID 映射到同目录 XAML 页面 ID。"""
    source_id = normalize_source_id(source_id)
    lowered = source_id.casefold()
    if lowered.endswith(".xaml.cs"):
        return normalize_page_id(source_id[:-3])
    if lowered.endswith(".cs"):
        return normalize_page_id(f"{source_id[:-3]}.xaml")
    raise ValueError(f"无法从非 C# 源码 ID 推导页面 ID: {source_id!r}")


def component_name_from_page_id(page_id: str) -> str:
    """返回路径派生的 TypeScript 组件符号，防止跨目录同名导入冲突。"""
    path = PurePosixPath(normalize_page_id(page_id))
    parts = [*path.parts[:-1], path.stem]
    encoded_parts = []
    for part in parts:
        encoded = re.sub(r"[^0-9A-Za-z_$]", "_", part)
        encoded_parts.append(encoded or "Page")
    identifier = "__".join(encoded_parts)
    if not identifier:
        identifier = "Page"
    if identifier[0].isdigit():
        identifier = f"Page_{identifier}"
    return identifier


def target_relative_path(source_id: str, suffix: str) -> Path:
    """把源码 ID 映射为保持相对目录结构的目标文件路径。"""
    if not suffix.startswith("."):
        raise ValueError(f"目标后缀必须以点开头: {suffix!r}")
    source = PurePosixPath(normalize_source_id(source_id))
    return Path(*source.with_suffix(suffix).parts)
