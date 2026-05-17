# -*- coding: utf-8 -*-
"""
Page Assembly Agent

负责将已迁移的根组件整合成完整的 React 页面。
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import PageAssemblyRequest, PageAssemblyResponse
from .utils import extract_tag_content, read_file_content, log_code_output, ensure_correct_export_name, get_available_resources, get_available_migrated_files, save_tsx_file, get_page_depended_by_count


class PageAssemblyAgent(BaseMigrationAgent):
    """
    页面整合 Agent
    
    职责：
    1. 接收已迁移的根组件代码
    2. 通过多轮渐进式修改整合成完整的 React 页面（按执行顺序）：
       - 第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面，确保函数签名格式正确
       - 第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
       - 第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑（可选）
       - 第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑（可选）
       - 第五轮：布局优化 - 确保整体布局正确，优化页面结构
       - 第六轮：子页面集成 - 确保子页面引用正确，集成子组件
       - 第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
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
                direct_dependencies=message.direct_dependencies,
                template=message.template,
                data=message.data
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
    
    async def _assemble_page(
        self,
        page_name: str,
        page_source: str,
        root_result: Dict[str, Any],
        page_layout_description: str,
        child_page_references: str,
        direct_dependencies: List[str],
        template: str = "",
        data: Dict[str, Any] = None
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
        self.logger.info(f"开始页面整合: {page_name}")
        
        # 获取可用的资源文件列表
        available_resources = get_available_resources(self.resources_dir)
        self.logger.debug(f"  可用资源文件: {available_resources}")
        
        # 创建临时文件路径用于存储每一轮的结果
        temp_tsx_path = self.result_dir / f"{page_name}_temp.tsx"
        
        # 提取根组件信息
        component_code = root_result.get("react_code", "")
        imports = root_result.get("imports", [])
        interfaces = root_result.get("interfaces", "")
        imports_text = "\n".join(imports) if isinstance(imports, list) else str(imports)
        
        # 获取已迁移的文件列表（用于验证可用的导入）
        available_files = get_available_migrated_files(self.result_dir)
        
        # 构建依赖页面导入说明（用于 prompt）
        dependency_imports_text = ""
        if direct_dependencies:
            dependency_imports_list = []
            for dep in direct_dependencies:
                dep_file = self.result_dir / f"{dep}.tsx"
                if dep_file.exists():
                    dependency_imports_list.append(f"- {dep}: Available (import already generated)")
                else:
                    dependency_imports_list.append(f"- {dep}: NOT AVAILABLE (file does not exist)")
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
        
        # ========== 多轮渐进式修改 ==========
        # 执行顺序：1.初始组装 2.资源修复 3.模板整合 4.数据整合 5.布局优化 6.子页面集成 7.代码规范
        
        # 在初始组装前，记录迁移后的根组件代码
        self.logger.info(f"  迁移后的根组件代码:")
        log_code_output("迁移后的根组件", page_name, component_code, self.logger)
        
        # 第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面，确保函数签名格式正确
        self.logger.info(f"  第一轮：初始组装...")
        page_code = await self._assemble_round_1_initial(
            page_name=page_name,
            component_code=component_code
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第一轮：初始组装完成")
        log_code_output("第一轮：初始组装", page_name, page_code, self.logger)
        
        # 第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
        if available_resources:
            page_code = await self._run_assembly_round(
                "第二轮：资源修复", temp_tsx_path, page_name,
                self._assemble_round_2_resources(
                    page_name=page_name,
                    resources_section=resources_section,
                    temp_tsx_path=temp_tsx_path,
                ),
            )
        else:
            self.logger.debug("  第二轮：资源修复（跳过：无资源文件）")

        # 第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑（如果存在）
        if template and template.strip():
            page_code = await self._run_assembly_round(
                "第三轮：模板整合", temp_tsx_path, page_name,
                self._assemble_round_3_template(
                    page_name=page_name,
                    template_code=template,
                    temp_tsx_path=temp_tsx_path,
                ),
            )
        else:
            self.logger.debug("  第三轮：模板整合（跳过：无模板依赖）")

        # 第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑（如果存在且包含必要信息）
        if data and isinstance(data, dict) and len(data) > 0:
            # 检查是否包含必要的数据依赖信息（迁移后的格式）
            if 'ts_code' in data and 'import_statement' in data:
                page_code = await self._run_assembly_round(
                    "第四轮：数据整合", temp_tsx_path, page_name,
                    self._assemble_round_4_data(
                        page_name=page_name,
                        data_info=data,
                        temp_tsx_path=temp_tsx_path,
                    ),
                )
            else:
                self.logger.debug("  第四轮：数据整合（跳过：缺少必要的数据依赖信息，需要 ts_code 和 import_statement）")
        else:
            self.logger.debug("  第四轮：数据整合（跳过：无数据依赖）")

        # 第五轮：布局优化 - 确保整体布局正确，优化页面结构
        page_code = await self._run_assembly_round(
            "第五轮：布局优化", temp_tsx_path, page_name,
            self._assemble_round_5_layout(
                page_name=page_name,
                page_source=page_source,
                page_layout_description=page_layout_description,
                temp_tsx_path=temp_tsx_path,
            ),
        )

        # 第六轮：子页面集成 - 确保子页面引用正确，集成子组件
        page_code = await self._run_assembly_round(
            "第六轮：子页面集成", temp_tsx_path, page_name,
            self._assemble_round_6_child_pages(
                page_name=page_name,
                child_page_references=child_page_references,
                dependency_imports_text=dependency_imports_text,
                direct_dependencies=direct_dependencies,
                temp_tsx_path=temp_tsx_path,
            ),
        )

        # 第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
        page_code = await self._run_assembly_round(
            "第七轮：代码规范", temp_tsx_path, page_name,
            self._assemble_round_7_code_style(
                page_name=page_name,
                temp_tsx_path=temp_tsx_path,
            ),
        )
        
        # 最终清理和验证
        self.logger.debug(f"  最终清理和验证...")
        page_code = ensure_correct_export_name(page_code, page_name, self.logger)
        self.logger.debug(f"  ✓ 最终清理和验证完成")
        log_code_output("最终清理和验证", page_name, page_code, self.logger)
        
        # 删除临时文件
        if temp_tsx_path.exists():
            try:
                temp_tsx_path.unlink()
                self.logger.debug(f"  ✓ 已删除临时文件: {temp_tsx_path}")
            except Exception as e:
                self.logger.warning(f"删除临时文件失败: {temp_tsx_path}, 错误: {e}")
        
        # 构建整合说明（按实际执行顺序）
        rounds_list = [
            "initial assembly",  # 第一轮
        ]
        if available_resources:
            rounds_list.append("resource fixing")  # 第二轮
        if template and template.strip():
            rounds_list.append("template integration")  # 第三轮
        if data and isinstance(data, dict) and len(data) > 0 and 'ts_code' in data and 'import_statement' in data:
            rounds_list.append("data integration")  # 第四轮
        rounds_list.extend([
            "layout optimization",  # 第五轮
            "child page integration",  # 第六轮
            "code style"  # 第七轮
        ])
        
        rounds_text = " THEN ".join(rounds_list)
        
        self.logger.info(f"✓ 页面整合完成: {page_name} (共 {len(rounds_list)} 轮: {rounds_text})")
        
        return {
            "page_code": page_code,
            "page_description": f"Complete React page for {page_name}",
            "assembly_notes": f"Page assembled through {len(rounds_list)} rounds: {rounds_text}. Exported as {page_name}."
        }

    async def _run_assembly_round(
        self,
        label: str,
        temp_tsx_path: Path,
        page_name: str,
        round_coro,
    ) -> str:
        """
        执行一个渐进式整合轮次（第 2~7 轮通用的样板逻辑）。

        此前第 2~7 轮各自重复了完全相同的"调用 → 空响应回退 → 保存 → 记录"
        六行代码。这里集中实现，日志文案、回退语义（解析失败时回退到上一轮
        的临时文件内容）与原逐轮实现逐字一致，因此不改变整合行为。

        第一轮（初始组装）是种子轮，没有"上一轮临时文件"可回退，故不走此路径。

        Args:
            label: 轮次中文标签，如 "第二轮：资源修复"
            temp_tsx_path: 跨轮共享的临时 tsx 文件路径
            page_name: 页面名（用于保存与日志）
            round_coro: 该轮的协程（在调用处构造，此处 await 执行）

        Returns:
            本轮产出的页面代码；若 LLM 响应解析失败则为上一轮临时文件内容
        """
        self.logger.info(f"  {label}...")
        page_code = await round_coro
        # 如果返回空字符串，使用上一轮的结果
        if not page_code or page_code.strip() == "":
            self.logger.warning(f"  {label} - LLM 响应解析失败，使用上一轮结果")
            page_code = read_file_content(temp_tsx_path)
        else:
            save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ {label}完成")
        log_code_output(label, page_name, page_code, self.logger)
        return page_code

    async def _assemble_round_1_initial(
        self,
        page_name: str,
        component_code: str
    ) -> str:
        """
        第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面
        
        此轮优先执行，基于已迁移的根组件代码创建完整的页面结构。
        组装所有组件代码、导入语句和接口定义，确保页面基本结构完整。
        最重要的是确保函数签名格式正确：MainWindow 使用 `export function MainWindow()`，
        其他页面使用 `export function PageName({ open, onClose }: PageNameProps)`。
        """
        # 判断是否是 MainWindow（根据依赖信息判断：depended_by_count == 0 表示根节点页面）
        dependency_file = self.dependency_dir / "page_dependency.json"
        depended_by_count = get_page_depended_by_count(dependency_file, page_name, self.logger)
        
        if depended_by_count is not None:
            # 如果依赖信息存在，根据 depended_by_count 判断
            is_main_window = (depended_by_count == 0)
            self.logger.info(f"  页面类型判断（基于依赖信息）: {page_name} - {'根页面 (depended_by_count=0)' if is_main_window else f'子页面 (depended_by_count={depended_by_count})'}")
        else:
            # 如果依赖信息不存在，回退到原来的逻辑
            is_main_window = page_name == "MainWindow" or "main" in page_name.lower() or "window" in page_name.lower()
            self.logger.info(f"  页面类型判断（基于名称匹配）: {page_name} - {'根页面' if is_main_window else '子页面'}")
        
        # 根据页面类型生成函数签名要求
        if is_main_window:
            function_signature_section = """## CRITICAL: Function Signature Format (MUST FOLLOW)

**For MainWindow pages, you MUST use this EXACT function signature:**

[TypeScript Code]
export function MainWindow() {
  // component code here
}
[/TypeScript Code]

**Rules:**
- **NO props interface** - MainWindow should NOT accept any props
- **NO React.FC** - Use function declaration, not React.FC
- **Function name**: Must be exactly "MainWindow"

**WRONG patterns to AVOID:**
- **DO NOT USE**: `interface Props { ... }`
- **DO NOT USE**: `const MainWindow: React.FC<Props> = (...) => { ... }`
- **DO NOT USE**: `export default function MainWindow(props: Props) { ... }`"""
        else:
            function_signature_section = f"""## CRITICAL: Function Signature Format (MUST FOLLOW)

**For Dialog/Modal pages, you MUST use this EXACT function signature:**

[TypeScript Code]
interface {page_name}Props {{
  open: boolean;
  onClose: () => void;
}}

export function {page_name}({{ open, onClose }}: {page_name}Props) {{
  // component code here
}}
[/TypeScript Code]

**Rules:**
- **Props interface**: Must define `{page_name}Props` with `open: boolean` and `onClose: () => void`
- **Function signature**: Must use destructuring `{{ open, onClose }}: {page_name}Props`
- **NO React.FC** - Use function declaration, not React.FC
- **Function name**: Must be exactly "{page_name}"
- **Parameter order**: `open` must come before `onClose`

**Function Signature Rules (STRICTLY ENFORCED):**
- **MUST use**: `export function {page_name}({{ open, onClose }}: {page_name}Props) {{ ... }}`
- **DO NOT use**: `export function {page_name}(props: {page_name}Props) {{ ... }}`
- **DO NOT use**: `export function {page_name}({{ open, onClose, ...otherProps }}: {page_name}Props) {{ ... }}`
- **DO NOT use**: `export const {page_name}: React.FC<{page_name}Props> = ({{ open, onClose }}) => {{ ... }}`
- **DO NOT add**: Additional parameters
- **DO NOT remove**: Either `open` or `onClose` from the function signature"""
        
        system_prompt = f"""You are an expert in React and TypeScript.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Correct the function signature of the provided component code to match the required format.

{function_signature_section}

## What you must do:
1. **CRITICAL**: Use the correct function signature format as specified above
2. **DO NOT modify** any other part of the code - only correct the function signature
3. **Preserve ALL** component logic, imports, interfaces, and TSX from the input
4. Ensure the component name matches the specified page name exactly
5. Put `export default PageName;` at the very end

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]
"""
        
        user_prompt = f"""Correct the function signature of this component:

[Page Name]
{page_name}
[/Page Name]

[Component Code]
{component_code}
[/Component Code]

CRITICAL REQUIREMENTS:
1. **ONLY correct the function signature** to match the format specified in the system prompt
2. **DO NOT modify** any other part of the code (logic, imports, interfaces, TSX)
3. Ensure component name is exactly "{page_name}" and export as `export default {page_name};`

Output the corrected TypeScript code with the proper function signature."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_2_resources(
        self,
        page_name: str,
        resources_section: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
        
        此轮在初始组装之后执行，确保所有资源引用（如图片、静态文件）使用正确的路径格式。
        修复硬编码或占位符路径，确保资源文件能够正确加载。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = """You are an expert in React resource management.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Fix all resource references in the component code to ensure they use the correct paths and React code.

## What you must do:
1. **Precise targeting**: Only locate and modify parts according to the task description (resource references)
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. Check for resource references (images, static files, etc.)
5. Replace hardcoded or placeholder paths with correct `/filename` format
6. Ensure image sources use `/filename.ext` format for files in public/ directory
7. Remove or fix any incorrect resource references
8. Preserve ALL existing functionality and logic
9. Do NOT change component name, imports, or export statement

## Resource Reference Guidelines:
- Use absolute paths starting with `/` for files in public/ directory
- Example: `/Watermark.png` for a file named `Watermark.png` in `public/`
- DO NOT use relative paths like `./public/filename.png`
- DO NOT use `process.env.PUBLIC_URL` unless specifically needed

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Resource only**: Only fix resource references
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Fix resource references in this React component:

[Page Name]
{page_name}
[/Page Name]

[Available Resources]
{resources_section}
[/Available Resources]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **Precise targeting**: Only locate and modify resource references according to the task description
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. Check for resource references (images, static files, etc.)
5. Replace hardcoded or placeholder paths with correct `/filename` format
6. Ensure image sources use `/filename.ext` format for files in public/ directory
7. Remove or fix any incorrect resource references
8. Preserve ALL existing functionality and logic
9. **CRITICAL**: Do NOT modify the function signature - it is already correct
10. Do NOT change component name, imports, or export statement

Output the modified TypeScript code."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_3_template(
        self,
        page_name: str,
        template_code: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑
        
        此轮在资源修复之后执行，整合根节点所需的模板代码。
        理解模板结构并将其正确集成到组件中，确保模板相关的导入和逻辑正确。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = """You are an expert in React component integration.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: The current migrated React code may be missing some formatting information. You need to integrate relevant component information and formatting information from the template into the current code.

**Important Note**: If the template contains invalid information or other information that cannot be directly migrated, you can ignore it directly.

## What you must do:
1. **Precise targeting**: Only locate and modify parts according to the task description (formatting information)
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. Identify missing formatting information in the current React code
5. Extract relevant component information and formatting information from the template
6. Integrate the template's component structure and formatting into the current code where appropriate
7. Ensure template-related imports are added if needed
8. Preserve ALL existing functionality and logic
9. Do NOT change component name, main structure, or export statement

## Template Integration Guidelines:
- Templates (DataTemplate/ControlTemplate) define how data should be rendered and formatted
- Extract component structure and formatting information from templates
- Integrate formatting information (layout, styling, component structure) into the current code
- Use appropriate MUI components based on template content
- Ensure data binding is correctly implemented
- **Ignore invalid or unmigratable information in the template**

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Template integration**: Integrate template logic appropriately
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Integrate the following template into this React component:

[Page Name]
{page_name}
[/Page Name]

[Template Code]
{template_code}
[/Template Code]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **Precise targeting**: Only locate and modify formatting information according to the task description
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. Identify missing formatting information in the current React code
5. Extract relevant component information and formatting information from the template
6. Integrate the template's component structure and formatting into the current code where appropriate
7. Ensure template-related imports are added if needed
8. Preserve ALL existing functionality and logic
9. **CRITICAL**: Do NOT modify the function signature - it is already correct
10. Do NOT change component name, main structure, or export statement
11. **Important**: If the template contains invalid information or other information that cannot be directly migrated, ignore it directly

Output the modified TypeScript code."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_4_data(
        self,
        page_name: str,
        data_info: Dict[str, Any],
        temp_tsx_path: Path
    ) -> str:
        """
        第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑
        
        此轮在模板整合之后执行，整合根节点所需的数据资源。
        只使用迁移后的数据格式（必须包含 ts_code 和 import_statement）。
        如果缺少必要的数据依赖信息，则跳过此轮，直接返回当前代码。
        确保数据导入语句正确，数据访问逻辑符合要求，使用正确的数据命名。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        # 检查是否包含必要的数据依赖信息（迁移后的格式）
        if not ('ts_code' in data_info and 'import_statement' in data_info):
            self.logger.warning(f"  数据整合跳过：缺少必要的数据依赖信息（需要 ts_code 和 import_statement）")
            return current_code
        
        # 使用迁移后的数据格式
        data_section = f"""[Data Resource - Import Statement]
{data_info.get('import_statement', '')}
[/Data Resource - Import Statement]

[Data Resource - TypeScript Code]
{data_info.get('ts_code', '')}
[/Data Resource - TypeScript Code]
"""
        
        system_prompt = """You are an expert in React data integration.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Integrate data resources into the React component.

## What you must do:
1. **Precise targeting**: Only locate and modify parts according to the task description (data integration)
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. Add the data import statement to the imports section
5. Use the imported data in the component where appropriate
6. Ensure data binding is correctly implemented
7. Preserve ALL existing functionality and logic
8. Do NOT change component name, main structure, or export statement

## Data Integration Guidelines:
- Add import statements at the top of the file
- Use the imported data constant in the component
- Ensure proper data binding and usage
- If the data is used for DataContext or similar, integrate it appropriately

## CRITICAL: Data Naming Requirements
**You MUST use the exact data names and property names as provided in the Data Resource section. Data naming errors will cause runtime failures.**

### Data Naming Convention (Reference: rag/ground-truth/src/data.ts):
- **Exported constants**: camelCase (e.g., `expenseData`, `costCenters`, `employees`)
- **Interfaces/Types**: PascalCase (e.g., `CostCenter`, `Employee`, `ExpenseReport`)
- **Object properties**: camelCase (e.g., `employeeNumber`, `lineItems`, `totalExpenses`)
- **DO NOT** change, modify, or rename any data names or property names
- Always use the exact names from the Data Resource TypeScript code

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Data integration**: Integrate data import and usage appropriately
- **CRITICAL - Data naming**: Use the exact data names and property names from the Data Resource section
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Integrate the following data resource into this React component:

[Page Name]
{page_name}
[/Page Name]

[Data Resource]
{data_section}
[/Data Resource]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **Precise targeting**: Only locate and modify data integration parts according to the task description
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. **CRITICAL - Data naming**: Use the exact data names and property names from the Data Resource section (do NOT modify any names)
5. Add the data import statement to the imports section
6. Use the imported data in the component where appropriate
7. Ensure data binding is correctly implemented
8. Preserve ALL existing functionality and logic
9. **CRITICAL**: Do NOT modify the function signature - it is already correct
10. Do NOT change component name, main structure, or export statement

Output the modified TypeScript code."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_5_layout(
        self,
        page_name: str,
        page_source: str,
        page_layout_description: str,
        temp_tsx_path: Path,
    ) -> str:
        """
        第五轮：布局优化 - 确保整体布局正确，优化页面结构
        
        此轮在数据整合之后执行，根据页面布局描述优化整体布局结构。
        比较原本的 WPF 页面代码和当前 React 代码在布局上的差异，修复组件迁移时可能遗漏的全局页面布局问题。
        确保组件布局符合原始 WPF 页面的布局要求，使用正确的 MUI 布局组件。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = """You are an expert in React and TypeScript UI layout.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Compare the original WPF page code with the current React code to identify layout differences, and fix any layout issues that may have been missed during component migration.

**Context**: During component migration, individual components may have been migrated correctly, but the overall page layout structure might not have been fully considered. This step is to fix and optimize the global page layout.

## What you must do:
1. **Precise targeting**: Only locate and modify parts according to the task description (layout structure)
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. **Compare layouts**: Compare the original WPF page code (XAML) with the current React code to identify layout differences
5. **Fix layout issues**: Fix any layout problems using common MUI layout components. **CRITICAL: DO NOT use `<Grid>` component** - Use `<Box>` with CSS Grid or Flexbox via `sx` prop, or use `<Stack>` for simple row/column layouts. Examples:
   - CSS Grid: `sx={ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2 }`
   - Flexbox: `sx={ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2 }`
   - Stack: `<Stack spacing={2} direction={ xs: 'column', md: 'row' }>`
6. **CRITICAL - No non-existent imports**: DO NOT import files that do not exist. If the code imports custom components that do not exist, you MUST:
   - Remove those import statements
   - Implement the corresponding components directly in the code
   - Do NOT assume any custom components exist unless they are explicitly provided
7. **Ensure correctness**: The modified React code MUST be correct and functional
8. Preserve ALL existing functionality and logic
9. Do NOT change imports, interfaces, component name, function signature, or child page integrations (except removing non-existent imports)

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here (do NOT wrap in backticks)
[/TypeScript Code]

## Critical Rules:
- **NO import statements**: DO NOT generate any import statements - they are already provided
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Layout only**: Only modify layout structure to match the description
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Compare the original WPF page code with the current React code to identify layout differences and fix them:

[Page Name]
{page_name}
[/Page Name]

[Original WPF Page Code (XAML)]
{page_source}
[/Original WPF Page Code (XAML)]

[Page Layout Description]
{page_layout_description}
[/Page Layout Description]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Compare the original WPF page code (XAML) with the current React code to identify layout differences
2. Use the Page Layout Description as a reference to understand the intended layout
3. Fix layout issues using common MUI layout components. **CRITICAL: DO NOT use `<Grid>` component** - Use `<Box>` with CSS Grid or Flexbox via `sx` prop, or use `<Stack>` for simple row/column layouts. Examples:
   - CSS Grid: `sx={{ display: 'grid', gridTemplateColumns: {{ xs: '1fr', md: 'repeat(2, 1fr)' }}, gap: 2 }}`
   - Flexbox: `sx={{ display: 'flex', flexDirection: {{ xs: 'column', md: 'row' }}, gap: 2 }}`
   - Stack: `<Stack spacing={{2}} direction={{ xs: 'column', md: 'row' }}>`
4. **CRITICAL - No non-existent imports**: DO NOT import files that do not exist. If the code imports custom components that do not exist, you MUST:
   - Remove those import statements
   - Implement the corresponding components directly in the code
   - Do NOT assume any custom components exist unless they are explicitly provided
5. Ensure the modified React code is correct and functional
6. Preserve ALL existing functionality and logic
7. **CRITICAL**: Do NOT modify the function signature, interfaces, component name, or child page integrations (except removing non-existent imports)

Output the modified TypeScript code."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_6_child_pages(
        self,
        page_name: str,
        child_page_references: str,
        dependency_imports_text: str,
        direct_dependencies: List[str] = None,
        temp_tsx_path: Path = None
    ) -> str:
        """
        第六轮：子页面集成 - 确保子页面引用正确，集成子组件
        
        此轮在布局优化之后执行，确保所有子页面组件正确集成。
        验证子页面导入和引用，使用正确的对话框交互模式（open/onClose），处理嵌套对话框。
        检查并修复交互式按钮/组件的逻辑，确保所有交互逻辑能正确触发。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        # Standard dialog interaction pattern - use open/onClose props
        state_example = "const [dialogOpen, setDialogOpen] = useState(false);"
        button_example = "<Button onClick={() => setDialogOpen(true)}>Open Dialog</Button>"
        dialog_example = "<ChildDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />"
        
        system_prompt = f"""You are an expert in React and TypeScript component integration.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Integrate child page components into the parent component based on the child page references analysis.

## Page Interaction Pattern (CRITICAL):

### For MainWindow Components:
- Use `useState` to manage dialog state: `{state_example}`
- Pass `open` and `onClose` props to child dialogs: `{dialog_example}`
- Use onClick handlers: `{button_example}`

### For Dialog/Modal Components:
- Use separate `useState` for each nested dialog
- Pass `open` and `onClose` props to nested dialogs
- Wrap nested dialogs in MUI `Dialog` component

## What you must do:
1. **Precise targeting**: Only locate and modify parts according to the task description (child page integration)
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. **MANDATORY**: Import ALL child page components using the import statements provided
5. **MANDATORY**: The code MUST include ALL child page components listed in Direct Dependencies - every page name must appear in the final TSX code
6. **Dialog pattern**: Use `useState` for dialog state, pass `open` and `onClose` props
7. **MUI Dialog**: Wrap dialog components in MUI `Dialog` component (if not already wrapped)
8. **CRITICAL - Interactive logic checking**: Check and fix interactive button/component logic to ensure all interactions work correctly:
   - **Button onClick handlers**: Verify all buttons have proper `onClick` handlers that trigger the intended actions
   - **Dialog open/close logic**: Ensure dialog state is correctly managed with `useState`, and `open`/`onClose` props are properly connected
   - **Event handler functions**: Check that all event handler functions (e.g., `handleOpen`, `handleClose`, `handleClick`) are defined and correctly bound
   - **State management**: Verify that `useState` hooks are properly initialized and state setters are correctly used
   - **Missing handlers**: If a button or interactive component lacks an `onClick` handler, add the appropriate handler function
   - **Incorrect handlers**: If a handler references a non-existent function or variable, fix it to use the correct state setter or handler
   - **Menu/Select interactions**: Ensure menu items, select dropdowns, and other interactive components have proper event handlers
9. Preserve ALL existing functionality and layout
10. Do NOT change component name, function signature, or export statement

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

## Critical Rules:
- **CRITICAL**: Every imported child page component MUST appear in the TSX code
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        # Format direct dependencies list
        direct_deps_text = "\n".join(direct_dependencies) if direct_dependencies else "None"
        
        user_prompt = f"""Integrate child page components into this React component:

[Page Name]
{page_name}
[/Page Name]

[Child Page Import Statements]
{dependency_imports_text}
[/Child Page Import Statements]

[Direct Dependencies]
{direct_deps_text}
[/Direct Dependencies]

[Child Page References]
{child_page_references}
[/Child Page References]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **MANDATORY**: Import ALL child page components listed in Child Page Import Statements
2. **MANDATORY**: The code MUST include ALL child page components listed in Direct Dependencies - every page name in Direct Dependencies must appear in the final TSX code
3. Follow the Page Interaction Pattern from system prompt:
   - MainWindow: Use `useState` for dialog state, pass `open` and `onClose` props
   - Dialog: Use separate `useState` for nested dialogs
4. **CRITICAL - Interactive logic checking**: Check and fix all interactive button/component logic to ensure all interactions work correctly:
   - **Button onClick handlers**: Verify all `<Button>`, `<IconButton>`, and other clickable components have proper `onClick` handlers
   - **Dialog state management**: Ensure dialog `open` state is correctly managed:
     - State declaration: `const [dialogOpen, setDialogOpen] = useState(false);`
     - Open handler: `onClick={{() => setDialogOpen(true)}}`
     - Close handler: `onClose={{() => setDialogOpen(false)}}`
     - Dialog prop: `open={{dialogOpen}}`
   - **Missing handlers**: If a button lacks an `onClick` handler, add the appropriate handler function
   - **Incorrect handlers**: If a handler references undefined functions or variables, fix it:
     - Replace undefined function calls with correct state setters
     - Ensure all handler functions are defined before use
     - Fix typos in function or variable names
   - **Menu interactions**: Ensure menu items have proper `onClick` handlers
   - **Form interactions**: Verify form buttons (submit, cancel) have proper handlers
   - **Navigation logic**: Check that navigation buttons correctly trigger page transitions or dialog opens
5. Example integration (from MainWindow.tsx):
[TypeScript Code]
// Import the child page component
import {{ CreateExpenseReportDialogBox }} from "./CreateExpenseReportDialogBox";

// Define state for dialog control
const [createDialogOpen, setCreateDialogOpen] = useState(false);

// Use the child page component in TSX
<CreateExpenseReportDialogBox
  open={{createDialogOpen}}
  onClose={{() => setCreateDialogOpen(false)}}
/>
[/TypeScript Code]

Output the modified TypeScript code."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_7_code_style(
        self,
        page_name: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
        
        此轮在初始组装之后执行，作为最后一轮优化，确保代码符合最佳实践。
        验证组件模式、组织导入顺序、确保代码结构规范，进行最终的代码质量检查。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = f"""You are an expert in React and TypeScript code style and best practices.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Ensure the code structure follows best practices and coding standards.

## What you must do:
1. **Precise targeting**: Only locate and modify parts according to the task description (code structure and style)
2. **Minimal changes**: Make minimal modifications only to necessary parts
3. **Do NOT break code**: Absolutely do NOT break or modify code in other locations
4. **Error checking and fixing**: Check for and fix common errors and non-standard usage:
   - **Unused Props interface**: If the component is a MainWindow (root page), it should NOT have a Props interface. MainWindow components should directly use global data (like `expenseData` from data imports), not receive props. Remove any unused Props interface.
   - **Naming conflicts**: Do NOT define variables or functions with the same name as the component (e.g., `const MainWindow = ...` inside a `MainWindow` component). Use proper naming patterns like `handleXxx` for event handlers (e.g., `handleCreateDialogOpen` instead of `const MainWindow = ...`).
   - **Unused declarations**: Remove any unused interfaces, types, variables, or imports that are declared but never used.
5. Organize code structure according to best practices
6. Preserve ALL existing functionality and logic
7. Do NOT change component name, function signature, or export statement

## Code Structure Requirements:
1. **Imports** - All imports at the top, organized: React → MUI → Child pages → Data → Others → Utilities, deduplicate
2. **Interfaces/Types** - After imports, before utility functions or component
3. **Utility Functions** - If any, place them before the component definition (write directly in file, do NOT import from non-existent files)
4. **Component** - The main component code
5. **Export** - `export default PageName;` at the very end

## Code Style Requirements:
- Use onClick handlers for all event bindings
- Prefer MUI standard components over custom wrappers
- Use proper TypeScript typing
- Clean, readable code with proper formatting

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

## Critical Rules:
- **Code structure**: imports → interfaces → utility functions → component → export
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Component name**: MUST match the page_name exactly
- **Export statement**: MUST be `export default PageName;` where PageName is the exact page name
"""
        
        user_prompt = f"""Ensure this React component follows code style and structure best practices:

[Page Name]
{page_name}
[/Page Name]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **CRITICAL**: Verify the component follows the Page Component Pattern (MainWindow vs Dialog/Modal)
2. **CRITICAL**: Do NOT modify the function signature - it is already correct
3. **CRITICAL - Error checking**: Check for and fix the following issues:
   - **Unused Props interface**: If this is a MainWindow component (root page), it should NOT have a Props interface. MainWindow components should directly use global data from imports (e.g., `expenseData`, `employees`, `costCenters`), not receive props. Remove any unused Props interface.
   - **Naming conflicts**: Check if there are any variables or functions with the same name as the component (e.g., `const {page_name} = ...` inside the component). If found, rename them to follow proper naming patterns (e.g., `handleXxx` for event handlers).
   - **Unused declarations**: Remove any unused interfaces, types, variables, or imports that are declared but never used in the code.
4. Ensure the component name is exactly "{page_name}" and export as `export default {page_name};`
5. Follow the code structure and style requirements from the system prompt

Output the modified TypeScript code."""
        
        response = await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
