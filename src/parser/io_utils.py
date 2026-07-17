"""
解析器共享的 JSON 读写工具。

整个 parser 子系统此前在 ~30 处重复了同一段
``open(..., encoding='utf-8') + json.load/dump(ensure_ascii=False, indent=2)``
代码。这里集中实现，输出字节与原实现完全一致（相同的 ``ensure_ascii``/
``indent`` 参数），因此属于纯结构性重构，不改变任何解析行为。
"""

import json
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, Path]


def read_json(path: PathLike) -> Any:
    """以 UTF-8 读取并解析一个 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: PathLike, data: Any, *, indent: int = 2) -> None:
    """
    将 ``data`` 写为 JSON 文件（UTF-8，``ensure_ascii=False``）。

    会自动创建父目录，行为与原先散落各处的
    ``mkdir(parents=True, exist_ok=True)`` + ``json.dump`` 一致。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
