"""
Component Migration Agent

负责将单个 WPF 组件迁移为 React 组件。
"""

import json
import re
from typing import Optional, List, Tuple

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig, build_json_system_prompt
from .base import BaseMigrationAgent
from .messages import ComponentMigrationRequest, ComponentMigrationResponse


class ComponentMigrateAgent(BaseMigrationAgent):
    """
    组件迁移 Agent
    
    职责：
    1. 接收 WPF 组件源代码
    2. 接收依赖代码和子组件 React 代码
    3. 接收 MUI 组件文档
    4. 使用 LLM 完成迁移
    5. 返回结构化的迁移结果
    """
    
    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        output_base_dir: str = "outputs"
    ):
        """
        初始化组件迁移 Agent
        
        Args:
            llm_config: LLM 配置（默认使用低档模型和 JSON mode）
            output_base_dir: 输出基础目录（用于日志配置）
        """
        # 初始化基类
        super().__init__(
            agent_type="ComponentMigrateAgent",
            llm_config=llm_config or LLMConfig.json_mode_config(),
            output_base_dir=output_base_dir
        )
        
        # 系统提示词
        self.system_message = self._build_system_prompt()
    
    def _parse_code_info(self, code: str) -> Tuple[str | None, List[str], str]:
        """
        从代码中解析提取组件名称、导入语句和接口定义
        
        Args:
            code: 完整的 TypeScript/TSX 代码
        
        Returns:
            (component_name, imports, interfaces) 元组
        """
        component_name = None
        imports = []
        interfaces = ""
        
        if not code.strip():
            return component_name, imports, interfaces
        
        # 提取 import 语句（支持多行 import）
        import_pattern = r'^import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)(?:\s*,\s*(?:\{[^}]*\}|\*\s+as\s+\w+|\w+))*\s+from\s+[\'"][^\'"]+[\'"]|[\'"][^\'"]+[\'"])\s*;?\s*$'
        for line in code.split('\n'):
            line_stripped = line.strip()
            if re.match(import_pattern, line_stripped, re.MULTILINE):
                import_line = line_stripped.rstrip(';').strip()
                if import_line:
                    imports.append(import_line)
        
        # 提取 interface/type 定义（支持多行）
        # 匹配 interface Name { ... } 或 type Name = ...
        interface_pattern = r'(?:interface|type)\s+\w+(?:\s*<[^>]*>)?\s*(?:extends\s+[^{]+)?\s*\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}'
        interface_matches = re.findall(interface_pattern, code, re.DOTALL)
        if interface_matches:
            interfaces = '\n\n'.join(interface_matches)
        
        # 提取组件名称（从 export function/const 中提取）
        # 匹配 export function ComponentName 或 export const ComponentName
        component_patterns = [
            r'export\s+function\s+(\w+)',  # 示例：export function ComponentName
            r'export\s+const\s+(\w+)\s*[:=]',  # 示例：export const ComponentName =
            r'export\s+default\s+function\s+(\w+)',  # 示例：export default function ComponentName
            r'const\s+(\w+)\s*[:=]\s*React\.FC',  # 示例：const ComponentName: React.FC
            r'function\s+(\w+)\s*\(',  # 示例：function ComponentName(
        ]
        
        for pattern in component_patterns:
            match = re.search(pattern, code)
            if match and match.group(1)[0].isupper():
                component_name = match.group(1)
                break
        
        return component_name, imports, interfaces
    
    def _build_system_prompt(self) -> str:
        """构建组件迁移系统提示词。"""
        return build_json_system_prompt(
            role="你是 WPF 到 React + TypeScript + Material-UI（MUI）的组件迁移专家。",
            goal="把单个 WPF 控件迁移为行为等价、依赖完整且可直接保存的 TSX 组件。",
            success_criteria=(
                "先识别控件用途、属性、binding、event 和布局，再选择最简单的等价 MUI 实现。",
                "完整保留输入中可识别的业务逻辑、数据绑定、事件和子组件关系，不添加原实现不存在的业务能力。",
                "输出包含全部必要 import、类型声明和组件实现，并只使用项目已声明的 React、MUI、Emotion 与 TypeScript API。",
                "提供 MUI 文档时，采用其中最简单且适用的 import、组件结构和 props；提供数据资源时，使用其精确名称与结构。",
            ),
            constraints=(
                "优先直接使用 MUI 标准组件；只在复杂业务逻辑、重复使用或独立 UI 模式确有需要时创建自定义组件。",
                "禁止使用 MUI Grid；网格布局使用 Box + CSS Grid/Flexbox，简单行列布局使用 Stack。",
                "Dialog 使用 Dialog、DialogTitle、DialogContent 和按需使用的 DialogActions，并采用 open/onClose 交互。",
                "binding 使用最简单的 React hooks，点击和导航优先使用 onClick。",
                "数据常量和属性使用 lower camelCase，类型与组件使用 PascalCase；DataGrid 每行必须有 id。",
                "不得虚构本地模块、未提供的数据字段或 MUI 文档之外的高级 API。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )

    @message_handler
    async def handle_migration_request(
        self, 
        message: ComponentMigrationRequest, 
        ctx: MessageContext
    ) -> ComponentMigrationResponse:
        """
        处理组件迁移请求
        
        Args:
            message: 组件迁移请求消息
            ctx: 消息上下文
        
        Returns:
            组件迁移响应消息
        """
        # 1. 构建用户提示词
        user_prompt = self._build_user_prompt(
            wpf_source=message.wpf_source,
            child_react_code=message.child_react_code,
            mui_components_docs=message.mui_components_docs,
            template=message.template,
            data=message.data
        )
        
        # 2. 调用 LLM，使用统一 JSON 输出与单次修复
        ts_code = await self.request_typescript_code(
            system_message=self.system_message,
            user_message=user_prompt,
        )
        if not ts_code:
            raise ValueError("组件迁移未返回有效 TypeScript 代码")

        # 3. 从代码中解析提取信息
        component_name, imports, interfaces = self._parse_code_info(ts_code)
        
        if component_name is None:
            raise ValueError("无法从生成代码中提取 PascalCase 组件名称")
        
        # 返回组件迁移响应
        return ComponentMigrationResponse(
            component_name=component_name,
            imports=imports,
            interfaces=interfaces,
            react_code=ts_code  # 完整的 TypeScript 代码
        )
    
    def _build_user_prompt(
        self,
        wpf_source: str,
        child_react_code: str,
        mui_components_docs: str,
        template: str = "",
        data: dict = None
    ) -> str:
        """构建组件迁移用户提示词。"""
        data = data or {}
        sections = [
            "# 任务",
            "将以下 WPF 控件迁移为 React + TypeScript + MUI 组件。",
            "",
            "## WPF 源码",
            "```xml",
            wpf_source,
            "```",
        ]

        if template and template.strip():
            sections.extend([
                "",
                "## 关联模板",
                "该模板用于理解数据结构、渲染逻辑和必要格式；无法可靠迁移的内容可以忽略。",
                "```xml",
                template,
                "```",
            ])

        if data:
            sections.extend(["", "## 数据资源"])
            if "ts_code" in data and "import_statement" in data:
                sections.extend([
                    "必须使用以下精确 import、常量名和对象结构，不得改名：",
                    "```typescript",
                    str(data.get("import_statement", "")),
                    str(data.get("ts_code", "")),
                    "```",
                ])
            else:
                sections.extend([
                    "以下是原始 WPF 数据资源，请将属性名转换为 lower camelCase：",
                    "```json",
                    json.dumps(data, ensure_ascii=False, indent=2),
                    "```",
                ])

        if child_react_code and child_react_code.strip():
            sections.extend([
                "",
                "## 已迁移子组件",
                "可直接复用以下子组件，不要虚构其他本地模块：",
                "```tsx",
                child_react_code,
                "```",
            ])

        if mui_components_docs and mui_components_docs.strip():
            sections.extend([
                "",
                "## MUI 参考文档",
                "严格采用文档示例中最简单的 import、组件结构和 props：",
                mui_components_docs,
            ])

        return "\n".join(sections)
