# -*- coding: utf-8 -*-
"""
Page Assembly Agent

负责将已迁移的根组件整合成完整的 React 页面。
使用多轮渐进式修改策略，逐步优化页面代码。
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import PageAssemblyRequest, PageAssemblyResponse


class PageAssemblyAgent(BaseMigrationAgent):
    """
    页面整合 Agent
    
    职责：
    1. 接收已迁移的根组件代码
    2. 通过多轮渐进式修改整合成完整的 React 页面：
       - 第一轮：初始组装
       - 第二轮：布局优化
       - 第三轮：子页面集成
       - 第四轮：资源修复
       - 第五轮：代码规范
    3. 返回完整的页面代码
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化页面整合 Agent
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（默认使用 gpt-4o，非 JSON 模式）
        """
        # 初始化基类（页面整合不需要 JSON 模式）
        super().__init__(
            agent_type="PageAssemblyAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",
                temperature=0,
                json_mode=False  # 页面整合必须使用纯文本模式
            ),
            output_base_dir=output_base_dir
        )
        
        # 项目配置
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        
        # 目录路径
        self.dependency_dir = self.output_base_dir / project_name / "dependency"
        self.result_dir = Path("result") / project_name
        self.resources_dir = self.result_dir / "public"  # 资源文件目录
    
    @message_handler
    async def handle_assembly_request(
        self,
        message: PageAssemblyRequest,
        ctx: MessageContext
    ) -> PageAssemblyResponse:
        """
        处理页面整合请求
        
        Args:
            message: 页面整合请求消息
            ctx: 消息上下文
        
        Returns:
            页面整合响应消息
        """
        try:
            # 执行页面整合
            result = await self._assemble_page(
                page_name=message.page_name,
                page_source=message.page_source,
                root_result={
                    "react_code": message.root_component,
                    "imports": message.root_imports,
                    "interfaces": message.root_interfaces
                },
                page_layout_description=message.page_layout_description,
                child_page_references=message.child_page_references,
                direct_dependencies=message.direct_dependencies
            )
            
            return PageAssemblyResponse(
                page_code=result["page_code"],
                page_description=result["page_description"],
                assembly_notes=result["assembly_notes"]
            )
            
        except Exception as e:
            return PageAssemblyResponse(
                page_code="",
                page_description="",
                assembly_notes=f"页面整合失败: {str(e)}"
            )
    
    def _get_available_resources(self) -> List[str]:
        """
        获取可用的资源文件列表
        
        Returns:
            资源文件名列表（不包括路径）
        """
        if not self.resources_dir.exists():
            return []
        
        resources = []
        for file_path in self.resources_dir.iterdir():
            if file_path.is_file():
                resources.append(file_path.name)
        
        return sorted(resources)
    
    async def _assemble_page(
        self,
        page_name: str,
        page_source: str,
        root_result: Dict[str, Any],
        page_layout_description: str,
        child_page_references: str,
        direct_dependencies: List[str]
    ) -> Dict[str, str]:
        """
        页面整合阶段：将根组件整合成完整的 React 页面（多轮渐进式修改）
        
        Args:
            page_name: 页面名称（最终导出的组件名必须与此相同）
            page_source: 完整的 WPF 页面源代码（XAML）
            root_result: 根组件的迁移结果
            page_layout_description: 页面布局描述
            child_page_references: 子页面引用分析
            direct_dependencies: 直接依赖页面列表
            
        Returns:
            整合后的页面代码字典
        """
        from src.llm import LLMClient, LLMConfig
        
        temp_config = LLMConfig(
            model=self.llm_client.config.model,
            temperature=self.llm_client.config.temperature,
            json_mode=False  # 页面整合必须使用纯文本模式
        )
        temp_client = LLMClient(config=temp_config)
        
        # 获取可用的资源文件列表
        available_resources = self._get_available_resources()
        self.logger.debug(f"  可用资源文件: {available_resources}")
        
        # 创建临时文件路径用于存储每一轮的结果
        temp_tsx_path = self.result_dir / f"{page_name}_temp.tsx"
        
        # 提取根组件信息
        component_code = root_result.get("react_code", "")
        imports = root_result.get("imports", [])
        interfaces = root_result.get("interfaces", "")
        imports_text = "\n".join(imports) if isinstance(imports, list) else str(imports)
        
        # 构建依赖页面导入说明
        dependency_imports_text = ""
        if direct_dependencies:
            dependency_imports_list = []
            for dep in direct_dependencies:
                dependency_imports_list.append(f"- {dep}: Import as `import {dep} from './{dep}';`")
            dependency_imports_text = "\n".join(dependency_imports_list)
        else:
            dependency_imports_text = "None"
        
        # 构建资源信息部分
        resources_section = ""
        if available_resources:
            resources_list = "\n".join([f"  - {res}" for res in available_resources])
            resources_section = f"""
Available Resources (in public/ directory):
{resources_list}

Note: Reference these resources using absolute paths starting with `/`, e.g., `/Watermark.png`
"""
        else:
            resources_section = """
Available Resources: None (no resources found in public/ directory)
"""
        
        # ========== 多轮渐进式修改 ==========
        # 第一轮：初始组装 - 基于根组件代码创建基本结构
        self.logger.debug("  第一轮：初始组装...")
        page_code = await self._assemble_round_1_initial(
            temp_client=temp_client,
            page_name=page_name,
            component_code=component_code,
            imports_text=imports_text,
            interfaces=interfaces,
            dependency_imports_text=dependency_imports_text
        )
        self._save_temp_tsx_file(temp_tsx_path, page_code, page_name)
        
        # 第二轮：布局优化 - 确保整体布局正确
        self.logger.debug("  第二轮：布局优化...")
        page_code = await self._assemble_round_2_layout(
            temp_client=temp_client,
            page_name=page_name,
            page_layout_description=page_layout_description,
            temp_tsx_path=temp_tsx_path
        )
        self._save_temp_tsx_file(temp_tsx_path, page_code, page_name)
        
        # 第三轮：子页面集成 - 确保子页面引用正确
        self.logger.debug("  第三轮：子页面集成...")
        page_code = await self._assemble_round_3_child_pages(
            temp_client=temp_client,
            page_name=page_name,
            child_page_references=child_page_references,
            dependency_imports_text=dependency_imports_text,
            temp_tsx_path=temp_tsx_path
        )
        self._save_temp_tsx_file(temp_tsx_path, page_code, page_name)
        
        # 第四轮：资源修复 - 确保资源引用正确
        self.logger.debug("  第四轮：资源修复...")
        page_code = await self._assemble_round_4_resources(
            temp_client=temp_client,
            page_name=page_name,
            resources_section=resources_section,
            available_resources=available_resources,
            temp_tsx_path=temp_tsx_path
        )
        self._save_temp_tsx_file(temp_tsx_path, page_code, page_name)
        
        # 第五轮：代码规范 - 确保代码结构符合规范
        self.logger.debug("  第五轮：代码规范...")
        page_code = await self._assemble_round_5_code_style(
            temp_client=temp_client,
            page_name=page_name,
            temp_tsx_path=temp_tsx_path
        )
        self._save_temp_tsx_file(temp_tsx_path, page_code, page_name)
        
        # 最终清理和验证
        page_code = self._ensure_correct_export_name(page_code, page_name)
        
        # 删除临时文件
        if temp_tsx_path.exists():
            try:
                temp_tsx_path.unlink()
                self.logger.debug(f"已删除临时文件: {temp_tsx_path}")
            except Exception as e:
                self.logger.warning(f"删除临时文件失败: {temp_tsx_path}, 错误: {e}")
        
        return {
            "page_code": page_code,
            "page_description": f"Complete React page for {page_name}",
            "assembly_notes": f"Page assembled through 5 rounds: initial assembly → layout optimization → child page integration → resource fixing → code style. Exported as {page_name}."
        }
    
    def _extract_code_from_markers(self, code: str) -> str:
        """
        从代码中提取标记内的内容
        
        支持的标记格式：
        - [TypeScript Code] ... [/TypeScript Code]
        - [TypeScript] ... [/TypeScript]
        - [TSX Code] ... [/TSX Code]
        - 其他 [...] ... [/...] 格式
        
        Args:
            code: 包含标记的代码字符串
            
        Returns:
            提取出的代码内容（去除标记）
        """
        import re
        
        cleaned_code = code.strip()
        
        # 优先处理 [TypeScript Code] ... [/TypeScript Code] 格式
        pattern = r'\[TypeScript\s+Code\]\s*\n?(.*?)\n?\[/TypeScript\s+Code\]'
        match = re.search(pattern, cleaned_code, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 处理 [TypeScript] ... [/TypeScript] 格式
        pattern = r'\[TypeScript\]\s*\n?(.*?)\n?\[/TypeScript\]'
        match = re.search(pattern, cleaned_code, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 处理 [TSX Code] ... [/TSX Code] 格式
        pattern = r'\[TSX\s+Code\]\s*\n?(.*?)\n?\[/TSX\s+Code\]'
        match = re.search(pattern, cleaned_code, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 处理通用的 [...] ... [/...] 格式（向后兼容）
        if cleaned_code.startswith("[") and "[/" in cleaned_code:
            pattern = r'\[.*?\]\s*\n?(.*?)\n?\[/.*?\]'
            match = re.search(pattern, cleaned_code, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # 处理 markdown ``` 格式（向后兼容）
        if cleaned_code.startswith("```"):
            lines = cleaned_code.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return '\n'.join(lines).strip()
        
        # 如果没有找到标记，返回原始代码
        return cleaned_code
    
    def _save_temp_tsx_file(self, temp_path: Path, code: str, page_name: str) -> None:
        """
        保存临时 TSX 文件并确保导出名称正确
        
        Args:
            temp_path: 临时文件路径
            code: TypeScript 代码（可能包含标记）
            page_name: 页面名称
        """
        # 提取标记内的代码
        cleaned_code = self._extract_code_from_markers(code)
        
        # 确保导出名称正确
        cleaned_code = self._ensure_correct_export_name(cleaned_code, page_name)
        
        # 保存文件
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_code)
    
    def _read_temp_tsx_file(self, temp_path: Path) -> str:
        """
        读取临时 TSX 文件
        
        Args:
            temp_path: 临时文件路径
            
        Returns:
            文件内容
        """
        if not temp_path.exists():
            raise FileNotFoundError(f"临时文件不存在: {temp_path}")
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    async def _assemble_round_1_initial(
        self,
        temp_client,
        page_name: str,
        component_code: str,
        imports_text: str,
        interfaces: str,
        dependency_imports_text: str
    ) -> str:
        """
        第一轮：初始组装 - 基于根组件代码创建基本结构
        """
        system_prompt = """You are an expert in React and TypeScript.

## Version Requirements
- **MUI (Material-UI)**: Use version 7.3.7
- **AutoGen**: Use version 0.7.5
- Ensure all imports and API usage are compatible with these specific versions

Your task: Assemble a migrated React component into a complete TypeScript page file with proper structure.

## What you must do:
1. Import ALL child page components listed in Direct Dependencies at the top
2. Put ALL other imports at the top (deduplicate if needed)
3. Put TypeScript interfaces after imports (if any)
4. Put the complete component code (with all its logic and TSX)
5. Ensure the component name matches the specified page name exactly
6. Put `export default PageName;` at the very end

## Critical Rules:
- **Output Format**: Output code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags
- **NO markdown code blocks**: Do NOT use ``` markdown format
- **NO JSON formatting**: Output only code, not JSON
- **NO explanatory text**: No comments or explanations outside the code tags
- **Preserve ALL logic**: Preserve ALL component logic and TSX from the input
- **Component name**: The component name MUST match the page_name exactly
- **Export statement**: MUST be `export default PageName;` where PageName is the exact page name
"""
        
        user_prompt = f"""Assemble this into a complete .tsx page file:

[Page Name] (must match export name)
{page_name}
[/Page Name]

[Direct Dependencies]
{dependency_imports_text}
[/Direct Dependencies]

[Root Component Code]
{component_code}
[/Root Component Code]

[Root Component Imports]
{imports_text}
[/Root Component Imports]

[Root Component Interfaces]
{interfaces}
[/Root Component Interfaces]

Requirements:
1. Import ALL child page components listed in Direct Dependencies at the top
2. Organize all other imports at the top (deduplicate)
3. Add interfaces after imports
4. Include the full component code
5. Ensure the component name is exactly "{page_name}"
6. Add "export default {page_name};" at the end

Output valid TypeScript code ready to save as {page_name}.tsx"""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码
        return self._extract_code_from_markers(response)
    
    async def _assemble_round_2_layout(
        self,
        temp_client,
        page_name: str,
        page_layout_description: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第二轮：布局优化 - 确保整体布局正确
        """
        current_code = self._read_temp_tsx_file(temp_tsx_path)
        
        system_prompt = """You are an expert in React and TypeScript UI layout.

## Version Requirements
- **MUI (Material-UI)**: Use version 7.3.7
- Ensure all imports and API usage are compatible with this version

Your task: Modify the existing React component to ensure the overall layout matches the provided layout description.

## What you must do:
1. Read the current component code carefully
2. Adjust the layout structure (Grid, Stack, Box, etc.) to match the layout description
3. Ensure visual hierarchy and spatial relationships are correct
4. Preserve ALL existing functionality and logic
5. Do NOT change imports, interfaces, or component name
6. Do NOT change child page integrations (if any)

## Critical Rules:
- **Output Format**: Output code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags
- **NO markdown code blocks**: Do NOT use ``` markdown format
- **NO explanatory text**: No comments or explanations outside the code tags
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Layout only**: Only modify layout structure to match the description
- **Keep unchanged**: Keep the component name and export statement unchanged
"""
        
        user_prompt = f"""Modify the layout of this React component to match the layout description:

[Page Name]
{page_name}
[/Page Name]

[Page Layout Description]
{page_layout_description}
[/Page Layout Description]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Adjust the layout structure to match the layout description
2. Ensure visual hierarchy and spatial relationships are correct
3. Preserve ALL existing functionality and logic
4. Do NOT change imports, interfaces, or component name
5. Do NOT change child page integrations (if any)

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码
        return self._extract_code_from_markers(response)
    
    async def _assemble_round_3_child_pages(
        self,
        temp_client,
        page_name: str,
        child_page_references: str,
        dependency_imports_text: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第三轮：子页面集成 - 确保子页面引用正确
        """
        current_code = self._read_temp_tsx_file(temp_tsx_path)
        
        onClick_example = "onClick={() => setShowDialog(true)}"
        button_example = "<Button onClick={() => setShowDialog(true)}>Open Dialog</Button>"
        tsx_example = "{showDialog && <CreateExpenseReportDialogBox onClose={() => setShowDialog(false)} />}"
        
        system_prompt = """You are an expert in React and TypeScript component integration.

## Version Requirements
- **MUI (Material-UI)**: Use version 7.3.7
- Ensure all imports and API usage are compatible with this version

Your task: Integrate child page components into the parent component based on the child page references analysis.

## What you must do:
1. **MANDATORY**: Import ALL child page components listed in Direct Dependencies
2. **MANDATORY**: Use ALL imported child page components in the TSX code
3. Use onClick handlers to control when child pages are shown/hidden
4. Use conditional rendering with state management
5. Preserve ALL existing functionality and layout
6. Do NOT change component name or export statement

## Critical Rules:
- **Output Format**: Output code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags
- **NO markdown code blocks**: Do NOT use ``` markdown format
- **NO explanatory text**: No comments or explanations outside the code tags
- **CRITICAL**: Every imported child page component MUST appear in the TSX code
- **Event handlers**: Use onClick handlers for all child page triggers
- **State management**: Use useState for state management
- **Keep unchanged**: Keep the component name and export statement unchanged
"""
        
        user_prompt = f"""Integrate child page components into this React component:

[Page Name]
{page_name}
[/Page Name]

[Direct Dependencies]
{dependency_imports_text}
[/Direct Dependencies]

[Child Page References]
{child_page_references}
[/Child Page References]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **MANDATORY**: Import ALL child page components listed in Direct Dependencies
2. **MANDATORY**: Use ALL imported child page components in the TSX code
3. Use onClick handlers to control when child pages are shown/hidden
4. Example: If `CreateExpenseReportDialogBox` is imported, you must:
   a) Define state: `const [showDialog, setShowDialog] = useState(false);`
   b) Add onClick handler: `{button_example}`
   c) Use it in TSX: `{tsx_example}`
5. Preserve ALL existing functionality and layout
6. Do NOT change component name or export statement

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码
        return self._extract_code_from_markers(response)
    
    async def _assemble_round_4_resources(
        self,
        temp_client,
        page_name: str,
        resources_section: str,
        available_resources: List[str],
        temp_tsx_path: Path
    ) -> str:
        """
        第四轮：资源修复 - 确保资源引用正确
        """
        current_code = self._read_temp_tsx_file(temp_tsx_path)
        
        system_prompt = """You are an expert in React resource management.

## Version Requirements
- **MUI (Material-UI)**: Use version 7.3.7
- Ensure all imports and API usage are compatible with this version

Your task: Fix all resource references in the component code to use correct paths.

## What you must do:
1. Check for resource references (images, static files, etc.)
2. Replace hardcoded or placeholder paths with correct `/filename` format
3. Ensure image sources use `/filename.ext` format for files in public/ directory
4. Remove or fix any incorrect resource references
5. Preserve ALL existing functionality and logic
6. Do NOT change component name, imports, or export statement

## Resource Reference Guidelines:
- Use absolute paths starting with `/` for files in public/ directory
- Example: `/Watermark.png` for a file named `Watermark.png` in `public/`
- DO NOT use relative paths like `./public/filename.png`
- DO NOT use `process.env.PUBLIC_URL` unless specifically needed

## Critical Rules:
- **Output Format**: Output code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags
- **NO markdown code blocks**: Do NOT use ``` markdown format
- **NO explanatory text**: No comments or explanations outside the code tags
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Resource only**: Only fix resource references
- **Keep unchanged**: Keep the component name and export statement unchanged
"""
        
        user_prompt = f"""Fix resource references in this React component:

[Page Name]
{page_name}
[/Page Name]

{resources_section}

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Check for resource references (images, static files, etc.)
2. Replace hardcoded or placeholder paths with correct `/filename` format
3. Ensure image sources use `/filename.ext` format for files in public/ directory
4. Remove or fix any incorrect resource references
5. Preserve ALL existing functionality and logic
6. Do NOT change component name, imports, or export statement

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码
        return self._extract_code_from_markers(response)
    
    async def _assemble_round_5_code_style(
        self,
        temp_client,
        page_name: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第五轮：代码规范 - 确保代码结构符合规范
        """
        current_code = self._read_temp_tsx_file(temp_tsx_path)
        
        system_prompt = """You are an expert in React and TypeScript code style and best practices.

## Version Requirements
- **MUI (Material-UI)**: Use version 7.3.7
- **AutoGen**: Use version 0.7.5
- Ensure all imports and API usage are compatible with these specific versions

Your task: Ensure the code structure follows best practices and coding standards.

## Code Structure Requirements:
1. **Imports** - All imports at the top, organized:
   - React imports first
   - MUI imports second
   - Child page component imports third
   - Other third-party imports fourth
   - Utility/helper imports last
   - Deduplicate imports
2. **Utility Functions** - If any utility functions exist, place them before the component definition
3. **Interfaces/Types** - After imports, before utility functions or component
4. **Component** - The main component code
5. **Export** - `export default PageName;` at the very end

## Code Style Requirements:
- Use onClick handlers for all event bindings (prefer onClick over other event handlers)
- Write utility functions, validators, and converters directly in the TSX file (do NOT import from non-existent files)
- Prefer MUI standard components over custom wrappers
- Use proper TypeScript typing
- Clean, readable code with proper formatting

## Critical Rules:
- **Output Format**: Output code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags
- **NO markdown code blocks**: Do NOT use ``` markdown format
- **NO explanatory text**: No comments or explanations outside the code tags
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Code structure**: Ensure proper structure: imports → interfaces → utility functions → component → export
- **Component name**: MUST match the page_name exactly
- **Export statement**: MUST be `export default PageName;` where PageName is the exact page name
- **MUI version**: Ensure all MUI imports and API calls are compatible with MUI v7.3.7
"""
        
        user_prompt = f"""Ensure this React component follows code style and structure best practices:

[Page Name]
{page_name}
[/Page Name]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Organize imports properly (React → MUI → Child pages → Others → Utilities)
2. Place utility functions before the component definition (if any)
3. Place interfaces after imports
4. Ensure proper code structure: imports → interfaces → utility functions → component → export
5. Use onClick handlers for all event bindings
6. Write utility functions directly in the file (do NOT import from non-existent files)
7. Prefer MUI standard components over custom wrappers
8. Ensure the component name is exactly "{page_name}"
9. Ensure the export statement is "export default {page_name};"
10. Preserve ALL existing functionality and logic

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码
        return self._extract_code_from_markers(response)
    
    def _ensure_correct_export_name(self, code: str, expected_name: str) -> str:
        """
        确保代码中的组件名和导出名与 page_name 一致
        
        Args:
            code: TypeScript 代码
            expected_name: 期望的组件名（page_name）
            
        Returns:
            修正后的代码
        """
        import re
        
        lines = code.split('\n')
        modified_lines = []
        component_declared = False
        component_name_found = None
        
        for line in lines:
            # 查找组件声明：const ComponentName: React.FC 或 const ComponentName = ...
            if not component_declared:
                # 匹配 const ComponentName: React.FC 或 const ComponentName = ...
                match = re.match(r'^(\s*)const\s+(\w+)\s*[:=]', line)
                if match:
                    indent = match.group(1)
                    old_name = match.group(2)
                    component_name_found = old_name
                    if old_name != expected_name:
                        # 替换组件名
                        line = re.sub(
                            r'^(\s*)const\s+\w+\s*',
                            f'{indent}const {expected_name} ',
                            line
                        )
                        component_declared = True
                        self.logger.debug(f"修正组件名: {old_name} -> {expected_name}")
                    else:
                        component_declared = True
            
            # 查找并修正 export default 语句
            if re.search(r'export\s+default\s+', line):
                # 替换为正确的导出名（处理 export default ComponentName; 或 export default ComponentName）
                line = re.sub(
                    r'export\s+default\s+\w+(\s*;)?',
                    f'export default {expected_name};',
                    line
                )
                self.logger.debug(f"修正导出名: -> {expected_name}")
            
            # 如果组件名已找到，替换代码中对组件名的引用（仅在 export default 之后）
            if component_name_found and component_name_found != expected_name:
                # 在 export default 之后，替换组件名引用
                if re.search(r'export\s+default\s+', line):
                    line = line.replace(component_name_found, expected_name)
            
            modified_lines.append(line)
        
        # 如果代码中没有找到 export default，添加它
        code_str = '\n'.join(modified_lines)
        if not re.search(r'export\s+default\s+', code_str):
            modified_lines.append(f'export default {expected_name};')
            self.logger.debug(f"添加导出语句: export default {expected_name};")
        
        return '\n'.join(modified_lines)

