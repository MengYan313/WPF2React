"""迁移领域的 LLM JSON 输出 schema。"""

TYPESCRIPT_CODE_SCHEMA = {
    "type": "object",
    "properties": {
        "typescript_code": {
            "type": "string",
            "description": "可直接保存的完整 TypeScript 或 TSX 源码",
        }
    },
    "required": ["typescript_code"],
    "additionalProperties": False,
}

DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "简洁的组件用途说明"}
    },
    "required": ["description"],
    "additionalProperties": False,
}

PAGE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "layout_description": {"type": "string", "description": "页面整体布局说明"},
        "child_page_references": {
            "type": "string",
            "description": "子页面引用位置和用途说明；没有时明确说明没有引用",
        },
    },
    "required": ["layout_description", "child_page_references"],
    "additionalProperties": False,
}

TYPESCRIPT_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "file_name": {"type": "string", "description": "不含路径的 TypeScript 文件名"},
        "description": {"type": "string", "description": "文件职责说明"},
        "public_interfaces": {
            "type": "array",
            "description": "文件导出的公共接口",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                    "reference": {
                        "type": "object",
                        "properties": {
                            "export_name": {"type": "string"},
                            "import_example": {"type": "string"},
                        },
                        "required": ["export_name", "import_example"],
                        "additionalProperties": False,
                    },
                },
                "required": ["name", "type", "description", "reference"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["file_name", "description", "public_interfaces"],
    "additionalProperties": False,
}
