# -*- coding: utf-8 -*-
"""
Page Migration Agent

负责协调整个页面的迁移，管理组件树的递归迁移过程。
使用消息传递与其他 Agent 通信（Autogen 最佳实践）。
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from autogen_core import MessageContext, message_handler, AgentId

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import (
    PageMigrationRequest, 
    PageMigrationResponse,
    MUISelectionRequest,
    MUISelectionResponse,
    ComponentMigrationRequest,
    ComponentMigrationResponse,
    PageAssemblyRequest,
    PageAssemblyResponse
)


class PageMigrateAgent(BaseMigrationAgent):
    """
    页面迁移 Agent
    
    职责：
    1. 加载和解析 control JSON 文件
    2. 递归遍历组件树（从叶子节点向上）
    3. 通过消息传递协调 MUISelectAgent 和 ComponentMigrateAgent
    4. 管理迁移结果的缓存和输出
    5. 生成最终的 React 页面代码
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化页面迁移 Agent
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（用于页面整合阶段）
        """
        # 初始化基类（需要 LLM 进行页面整合）
        super().__init__(
            agent_type="PageMigrateAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",
                temperature=0,
                json_mode=False  # 页面整合不需要 JSON 模式
            ),
            output_base_dir=output_base_dir
        )
        
        # 项目配置
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        
        # 迁移缓存（使用节点路径作为唯一标识）
        self.migration_cache: Dict[str, Dict[str, Any]] = {}
        
        # 目录路径
        self.dependency_dir = self.output_base_dir / project_name / "dependency"
        self.migration_dir = self.output_base_dir / project_name / "migration"  # JSON 文件存储目录（实验记录）
        # TSX 文件存储目录（最终迁移结果）
        self.result_dir = Path("result") / project_name
        self.resources_dir = self.result_dir / "public"  # 资源文件目录
    
    @message_handler
    async def handle_page_migration_request(
        self, 
        message: PageMigrationRequest, 
        ctx: MessageContext
    ) -> PageMigrationResponse:
        """
        处理页面迁移请求
        
        Args:
            message: 页面迁移请求消息
            ctx: 消息上下文
        
        Returns:
            页面迁移响应消息
        """
        try:
            # 清空缓存
            self.migration_cache.clear()
            
            # 确定 control JSON 文件路径
            if message.control_json_path:
                control_json_path = message.control_json_path
            else:
                # 使用页面名称构建路径
                control_json_path = str(
                    self.dependency_dir / f"control_{message.page_name}.json"
                )
            
            # 执行迁移
            result = await self._migrate_page_from_control_json(
                control_json_path=control_json_path,
                ctx=ctx
            )
            
            # 生成输出
            output_path = self._generate_output(
                page_name=message.page_name,
                result=result,
                output_dir=message.output_dir
            )
            
            return PageMigrationResponse(
                page_name=message.page_name,
                total_components=result.get("total_components", 0),
                migrated_components=len(self.migration_cache),
                output_path=output_path,
                success=True
            )
            
        except Exception as e:
            return PageMigrationResponse(
                page_name=message.page_name,
                total_components=0,
                migrated_components=0,
                output_path="",
                success=False,
                error=str(e)
            )
    
    async def _migrate_page_from_control_json(
        self,
        control_json_path: str,
        ctx: MessageContext
    ) -> Dict[str, Any]:
        """
        从 control JSON 文件迁移整个页面
        
        Args:
            control_json_path: control JSON 文件路径
            ctx: 消息上下文（用于 Agent 通信）
        
        Returns:
            迁移结果字典
        """
        # 1. 加载 control JSON
        control_data = self._load_control_json(control_json_path)
        
        # 2. 提取根节点和树结构
        # 注意：字段名为 "controls"（不是 "tree"）和 "control_count"（不是 "total"）
        tree = control_data.get("controls", {})
        total_components = control_data.get("control_count", 0)
        root_tag = tree.get("tag", "") if tree else ""
        page_name = Path(control_json_path).stem.replace("control_", "")
        
        if not tree:
            raise ValueError(f"control JSON 中没有 controls 结构: {control_json_path}")
        
        # 日志：页面迁移开始
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移页面: {page_name}")
        self.logger.debug(f"  根标签: <{root_tag}>")
        self.logger.debug(f"  总组件数: {total_components}")
        self.logger.debug(f"  迁移策略: 自底向上递归")
        self.logger.info(f"{'='*80}\n")
        
        # 3. 递归迁移整个组件树（组件迁移阶段）
        root_result = await self._migrate_node_recursive(
            node=tree,
            node_path="root",
            wpf_dependencies="",
            ctx=ctx
        )
        
        # 日志：组件迁移完成
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"组件迁移完成: {page_name}")
        self.logger.debug(f"  已迁移组件数: {len(self.migration_cache)}")
        self.logger.debug(f"  根组件: {root_result.get('component_name', 'Unknown')}")
        self.logger.info(f"{'='*80}\n")
        
        # 4. 页面整合阶段：将根组件整合成完整页面
        self.logger.info("开始页面整合...")
        page_source = tree.get("source_code", "")
        assembled_page = await self._assemble_page(
            page_name=page_name,
            page_source=page_source,
            root_result=root_result
        )
        
        # 用整合后的页面代码替换根组件的 react_code
        root_result["react_code"] = assembled_page["page_code"]
        root_result["description"] = assembled_page["page_description"]
        root_result["migration_notes"] = assembled_page["assembly_notes"]
        
        self.logger.info("页面整合完成")
        self.logger.info(f"{'='*80}\n")
        
        return {
            "page_name": Path(control_json_path).stem.replace("control_", ""),
            "root_tag": root_tag,
            "total_components": total_components,
            "root_component": root_result
        }
    
    async def _migrate_node_recursive(
        self,
        node: Dict[str, Any],
        node_path: str,
        wpf_dependencies: str,
        ctx: MessageContext
    ) -> Dict[str, Any]:
        """
        递归迁移节点及其子节点
        
        Args:
            node: 节点数据
            node_path: 节点路径（唯一标识）
            wpf_dependencies: WPF 依赖代码
            ctx: 消息上下文（用于 Agent 通信）
        
        Returns:
            迁移结果字典
        """
        # 检查缓存
        if node_path in self.migration_cache:
            return self.migration_cache[node_path]
        
        # 提取节点信息
        wpf_tag = node.get("tag", "")
        xaml_code = node.get("source_code", "")  # 注意：字段名为 "source_code"
        children = node.get("children", [])
        
        # 日志：开始处理节点
        indent = "  " * node_path.count(".")
        self.logger.debug(f"{indent}[{node_path}] <{wpf_tag}> (子组件: {len(children)})")
        
        # 1. 先递归迁移所有子节点
        child_results = []
        
        for idx, child in enumerate(children):
            child_path = f"{node_path}.{idx}"
            child_result = await self._migrate_node_recursive(
                node=child,
                node_path=child_path,
                wpf_dependencies=wpf_dependencies,
                ctx=ctx
            )
            child_results.append(child_result)
        
        # 2. 合并子组件的 React 代码
        child_react_code = self._merge_child_react_code(child_results)
        
        # 3. 通过消息传递请求 MUISelectAgent 选择组件
        mui_request = MUISelectionRequest(
            wpf_source=xaml_code,
            wpf_tag=wpf_tag,
            max_components=3
        )
        
        # 发送消息到 MUISelectAgent
        mui_response = await self.send_message(
            message=mui_request,
            recipient=AgentId(type="MUISelectAgent", key="default"),
            cancellation_token=ctx.cancellation_token
        )
        
        # 显示选择的 MUI 组件
        mui_components_str = ', '.join(mui_response.selected_components) if mui_response.selected_components else '(无)'
        self.logger.debug(f"{indent}  MUI: [{mui_components_str}]")
        
        # 4. 通过消息传递请求 ComponentMigrateAgent 迁移组件
        migrate_request = ComponentMigrationRequest(
            wpf_source=xaml_code,
            dependencies_code=wpf_dependencies,
            child_react_code=child_react_code,
            mui_components_docs=mui_response.docs
        )
        
        # 发送消息到 ComponentMigrateAgent
        migrate_response = await self.send_message(
            message=migrate_request,
            recipient=AgentId(type="ComponentMigrateAgent", key="default"),
            cancellation_token=ctx.cancellation_token
        )
        
        # 显示迁移结果（输出完整描述，不截断）
        self.logger.debug(f"{indent}  => {migrate_response.component_name}: {migrate_response.description}")
        
        # 5. 构建结果
        result = {
            "node_path": node_path,
            "wpf_tag": wpf_tag,
            "component_name": migrate_response.component_name,
            "description": migrate_response.description,
            "react_code": migrate_response.react_code,
            "imports": migrate_response.imports,
            "interfaces": migrate_response.interfaces,
            "migration_notes": migrate_response.migration_notes,
            "selected_mui_components": mui_response.selected_components,
            "children": child_results
        }
        
        # 6. 缓存结果
        self.migration_cache[node_path] = result
        
        return result
    
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
        root_result: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        页面整合阶段：将根组件整合成完整的 React 页面（三阶段）
        
        第一阶段：从 page_dependency.json 获取直接依赖页面和 C# 文件路径
        第二阶段：分析页面布局和子页面引用位置（XAML + C#）
        第三阶段：使用布局描述和子页面引用信息进行页面整合
        
        Args:
            page_name: 页面名称（最终导出的组件名必须与此相同）
            page_source: 完整的 WPF 页面源代码（XAML）
            root_result: 根组件的迁移结果
            
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
        
        # ========== 第一阶段：获取直接依赖页面和 C# 文件路径 ==========
        self.logger.debug("第一阶段：获取直接依赖页面和 C# 文件路径...")
        
        dependency_file = self.dependency_dir / "page_dependency.json"
        if not dependency_file.exists():
            raise FileNotFoundError(
                f"依赖文件不存在: {dependency_file}\n"
                f"请先运行页面依赖分析: python -m src.parser.page_dependency"
            )
        
        with open(dependency_file, 'r', encoding='utf-8') as f:
            dependency_graph = json.load(f)
        
        pages_info = dependency_graph.get('pages', {})
        page_info = pages_info.get(page_name, {})
        
        # 获取直接依赖页面（不包括更深层的节点）
        direct_dependencies = page_info.get('dependencies', [])
        cs_file_path = page_info.get('cs_file', '')
        
        self.logger.debug(f"  直接依赖页面: {direct_dependencies}")
        self.logger.debug(f"  C# 文件路径: {cs_file_path}")
        
        # 读取 C# 文件内容
        cs_source_code = ""
        if cs_file_path:
            cs_path = Path(cs_file_path)
            if cs_path.exists():
                try:
                    with open(cs_path, 'r', encoding='utf-8') as f:
                        cs_source_code = f.read()
                except UnicodeDecodeError:
                    # 尝试其他编码
                    with open(cs_path, 'r', encoding='latin-1') as f:
                        cs_source_code = f.read()
                self.logger.debug(f"  成功读取 C# 文件: {len(cs_source_code)} 字符")
            else:
                self.logger.warning(f"  C# 文件不存在: {cs_path}")
        
        # ========== 第二阶段：分析页面布局和子页面引用位置 ==========
        self.logger.debug("第二阶段：分析页面布局和子页面引用位置...")
        
        layout_system_prompt = """You are an expert in UI/UX analysis and code analysis.

Your task: Analyze the WPF page source code (XAML) and C# code-behind file to:
1. Describe the overall layout structure in natural language
2. Identify where dependent child pages are referenced and used

## Requirements:

### Layout Description:
1. Describe the page layout from a user's perspective (what they see and how elements are arranged)
2. Focus on visual structure, spatial relationships, and functional areas
3. DO NOT mention specific WPF component names (like Button, TextBox, Grid, etc.)
4. Use natural language to describe:
   - Overall page structure (e.g., "header at top, main content in center, sidebar on left")
   - Layout patterns (e.g., "form with multiple input fields arranged in rows")
   - Visual hierarchy (e.g., "title at top, followed by content sections")
   - Functional areas (e.g., "navigation bar, content area, footer")

### Child Page References:
1. Analyze the C# code to identify where dependent child pages are instantiated or referenced
2. Describe the context and purpose of each child page reference:
   - Where in the code flow is the child page created/opened?
   - What triggers the child page to be shown?
   - What is the relationship between the parent page and child page?
   - What data or context is passed to the child page?

## Output Format:

Provide your analysis in two sections:

**Layout Description:**
[Your layout description here]

**Child Page References:**
[Your analysis of child page references here. If no child pages are referenced, state "No child pages are referenced in this page."]

Output ONLY the analysis text, no code, no markdown formatting, no explanations."""
        
        layout_user_prompt = f"""Analyze this WPF page:

**XAML Source Code:**
{page_source}

**C# Code-Behind:**
{cs_source_code if cs_source_code else "(C# file not found or empty)"}

**Direct Dependencies (Child Pages):**
{', '.join(direct_dependencies) if direct_dependencies else 'None'}

Please provide:
1. Layout description in natural language (focus on visual structure, do not mention WPF component names)
2. Analysis of where and how child pages are referenced in the code (if any)"""
        
        layout_analysis = await temp_client.create(
            messages=[
                {"role": "system", "content": layout_system_prompt},
                {"role": "user", "content": layout_user_prompt}
            ]
        )
        
        layout_analysis = layout_analysis.strip()
        self.logger.debug(f"布局和子页面引用分析:\n{layout_analysis}")
        
        # 解析布局描述和子页面引用说明
        page_layout_description = ""
        child_page_references = ""
        
        if "**Layout Description:**" in layout_analysis:
            parts = layout_analysis.split("**Layout Description:**", 1)
            if len(parts) > 1:
                remaining = parts[1]
                if "**Child Page References:**" in remaining:
                    layout_part, ref_part = remaining.split("**Child Page References:**", 1)
                    page_layout_description = layout_part.strip()
                    child_page_references = ref_part.strip()
                else:
                    page_layout_description = remaining.strip()
        elif "**Child Page References:**" in layout_analysis:
            parts = layout_analysis.split("**Child Page References:**", 1)
            child_page_references = parts[1].strip() if len(parts) > 1 else ""
        else:
            # 如果没有明确的分隔符，假设整个内容是布局描述
            page_layout_description = layout_analysis
        
        if not page_layout_description:
            page_layout_description = "Standard page layout structure."
        
        if not child_page_references:
            child_page_references = "No child pages are referenced in this page."
        
        # ========== 第三阶段：使用布局描述和子页面引用信息进行页面整合 ==========
        self.logger.debug("第三阶段：使用布局描述和子页面引用信息进行页面整合...")
        
        # 获取可用的资源文件列表
        available_resources = self._get_available_resources()
        self.logger.debug(f"  可用资源文件: {available_resources}")
        
        # 构建资源信息文本
        resources_info_text = ""
        if available_resources:
            resources_list = "\n".join([f"  - {res}" for res in available_resources])
            resources_info_text = f"""
## Available Resources

The following resource files are available in the `public/` directory:
{resources_list}

### Resource Reference Guidelines:

1. **Image files** (png, jpg, jpeg, gif, svg, etc.):
   - Use: `<img src="/filename.png" alt="description" />` (replace filename.png with actual resource name)
   - Or with MUI Box: `<Box component="img" src="/filename.png" alt="description" />`
   - In React, files in the `public/` directory are served from the root path `/`

2. **Other static files**:
   - Reference them using the root path: `/filename.ext`
   - Example: `/Watermark.png` for a file named `Watermark.png` in `public/`

3. **Important**:
   - DO NOT use relative paths like `./public/filename.png` or `../public/filename.png`
   - DO NOT use `process.env.PUBLIC_URL` unless specifically needed (it's usually not needed for Create React App)
   - Use absolute paths starting with `/` for files in the `public/` directory
   - Check the component code for any resource references and ensure they use the correct paths
   - If you find hardcoded paths like `path/to/watermark.png` or placeholder paths, replace them with the correct `/filename` format
"""
        else:
            resources_info_text = """
## Available Resources

No resource files are currently available in the `public/` directory.
If the component code references image or other resource files, you may need to:
1. Check if the resource files exist and are properly referenced
2. Use placeholder paths or remove resource references if resources are not available
"""
        
        # 构建系统提示词（使用字符串拼接而不是 f-string，避免嵌套 f-string 的花括号冲突）
        base_prompt = """You are an expert in React and TypeScript.

## Version Requirements

- **MUI (Material-UI)**: Use version 7.3.7
- **AutoGen**: Use version 0.7.5
- Ensure all imports and API usage are compatible with these specific versions

Your task: Assemble a migrated React component into a complete, properly formatted TypeScript page that correctly references and uses dependent child pages.

## What you must do:

1. Import dependent child page components at the top (if any)
   - Import from the migration output directory: `import ChildPageName from './ChildPageName';`
   - Only import pages that are listed in the direct dependencies
   - **CRITICAL**: If you import a child page component, you MUST use it in the component code
   - Do NOT import child page components that are not used in the code
   - If a child page is listed in dependencies, it MUST be imported AND used in the component
2. Put ALL other imports at the top (deduplicate if needed)
3. Put TypeScript interfaces after imports (if any)
4. Put the complete component code (with all its logic and TSX)
5. Ensure the component name matches the specified page name exactly
6. Properly integrate child page components based on the child page references analysis
   - **MANDATORY**: If a child page component is imported, it MUST appear in the TSX code
   - Use child page components appropriately (e.g., conditional rendering, event handlers, etc.)
   - Example: If `CreateExpenseReportDialogBox` is imported, it must be used like `<CreateExpenseReportDialogBox ... />` or `{{showDialog && <CreateExpenseReportDialogBox ... />}}`
     - Always define state first: `const [showDialog, setShowDialog] = useState(false);`
7. Put `export default PageName;` at the very end (where PageName is the exact page name provided)

## Example Output Structure:

```typescript
import React, { useState } from 'react';
import { Button, TextField } from '@mui/material';
import CreateExpenseReportDialogBox from './CreateExpenseReportDialogBox';

interface MyProps {
  name: string;
}

const MainWindow: React.FC<MyProps> = ({ name }) => {
  const [showDialog, setShowDialog] = useState(false);
  
  const handleOpenDialog = () => {
    setShowDialog(true);
  };
  
  return (
    <div>
      <Button onClick={handleOpenDialog}>Open Dialog</Button>
      {/* IMPORTANT: CreateExpenseReportDialogBox is imported, so it MUST be used */}
      {showDialog && <CreateExpenseReportDialogBox onClose={() => setShowDialog(false)} />}
    </div>
  );
};

export default MainWindow;
```

**Key Points:**
- `CreateExpenseReportDialogBox` is imported, so it MUST be used in the TSX code
- If a child page component is imported but not used, either remove the import or add the usage
- Use state management (useState) to control when child pages are shown/hidden
- Pass appropriate props to child page components based on the original WPF behavior

## Critical Rules:

- Output ONLY valid TypeScript/React code
- NO markdown code blocks (no ```)
- NO JSON formatting
- NO explanatory text or comments outside the code
- Preserve ALL component logic and TSX from the input
- Import child page components correctly from the same directory
- **CRITICAL**: If you import a child page component, you MUST use it in the component code
- Do NOT import child page components that are not used
- Integrate child pages based on the child page references analysis
- All imported child page components MUST appear in the TSX code
- Only organize structure (imports → interfaces → component → export)
- The component name MUST match the page_name exactly
- The export statement MUST be `export default PageName;` where PageName is the exact page name
- Ensure all MUI imports and API calls are compatible with MUI v7.3.7

## IMPORTANT: Prefer MUI Standard Components

When assembling the page, if you see references to custom components that are simple wrappers around MUI components, replace them with direct MUI component usage:

- Replace custom `<CloseButton>` with `<Button>` from `@mui/material`
- Replace custom `<OkButton>` with `<Button>` from `@mui/material`
- Replace custom `<WatermarkImage>` with `<img>` or `<Box component="img">` from `@mui/material`
- Replace custom `<ExpenseReportChart>` with appropriate MUI chart components if available
- Replace custom `<TotalExpensesContainer>` with `<Box>` or `<Stack>` from `@mui/material`
- Replace any other simple wrapper components with their MUI equivalents directly

Only keep custom component imports if they represent meaningful business logic or complex UI patterns that cannot be expressed inline.

"""
        
        resource_fixing_section = """
## Resource Reference Checking and Fixing

When assembling the page, you MUST:

1. **Check for resource references** in the component code:
   - Look for image references (img src, background-image, etc.)
   - Look for hardcoded paths like `path/to/watermark.png`, `watermark.png`, or placeholder paths
   - Look for any references to resource files

2. **Fix resource references**:
   - Replace hardcoded or placeholder paths with correct `/filename` format
   - Ensure image sources use the correct path format: `/filename.ext`
   - If a resource file is referenced but not in the available resources list, either:
     a) Remove the reference if it's not critical
     b) Use a placeholder path with a comment indicating the resource needs to be added
   - Ensure all resource references follow React best practices for public assets

3. **Examples of fixes**:
   - `src='path/to/watermark.png'` → `src='/Watermark.png'` (if Watermark.png exists in resources)
   - `<WatermarkImage imageSrc='path/to/watermark.png' />` → `<Box component="img" src="/Watermark.png" alt="Watermark" />` (if Watermark.png exists)
   - `backgroundImage: 'url(watermark.png)'` → `backgroundImage: 'url(/Watermark.png)'`

Your response must be pure TypeScript code that can be directly saved to a .tsx file."""
        
        # 拼接完整的系统提示词
        assembly_system_prompt = base_prompt + resources_info_text + resource_fixing_section
        
        # 提取根组件信息
        component_code = root_result.get("react_code", "")
        imports = root_result.get("imports", [])
        interfaces = root_result.get("interfaces", "")
        
        # 构建用户提示
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
        
        assembly_user_prompt = f"""Assemble this into a complete .tsx page file:

Page Name (must match export name): {page_name}

Direct Dependencies (Child Pages):
{dependency_imports_text}

Page Layout Description:
{page_layout_description}

Child Page References Analysis:
{child_page_references}

{resources_section}

Root Component Code:
{component_code}

Root Component Imports:
{imports_text}

Root Component Interfaces:
{interfaces}

---

Requirements:
1. Import dependent child page components at the top (if any)
   - Use relative imports: `import ChildPageName from './ChildPageName';`
   - Only import pages listed in Direct Dependencies above
   - **CRITICAL**: If you import a child page component, you MUST use it in the component code
   - Do NOT import child page components that are not used
   - If a child page is listed in Direct Dependencies, it MUST be imported AND used in the TSX code
2. Organize all other imports at the top (deduplicate)
3. Add interfaces after imports
4. Include the full component code
5. Integrate child page components based on the Child Page References Analysis
   - **MANDATORY**: All imported child page components MUST appear in the TSX code
   - Use child page components appropriately (e.g., conditional rendering with state, event handlers, etc.)
   - Example: If `CreateExpenseReportDialogBox` is imported, you must:
     a) Define state: `const [showDialog, setShowDialog] = useState(false);`
     b) Use it in TSX: `{{showDialog && <CreateExpenseReportDialogBox onClose={{() => setShowDialog(false)}} />}}`
     c) Add event handler: `onClick={{() => setShowDialog(true)}}`
   - If the child page is referenced in the analysis but not yet integrated, add appropriate state management and rendering logic
   - **IMPORTANT**: Always define state variables before using them in conditional rendering
6. Ensure the component name is exactly "{page_name}"
7. Add "export default {page_name};" at the end (not the root component name)
8. Ensure all MUI imports and API usage are compatible with MUI v7.3.7
9. If AutoGen is used, ensure compatibility with AutoGen v0.7.5
10. The final exported component should reflect the page layout and properly use child pages as described
    - **VERIFY**: Check that every imported child page component is actually used in the TSX code
    - If a child page is imported but not used, either remove the import or add the usage
11. **CRITICAL**: Check and fix all resource references in the code:
    - Replace hardcoded or placeholder paths with correct `/filename` format
    - Ensure image sources use `/filename.ext` format for files in public/ directory
    - Remove or fix any incorrect resource references

Output valid TypeScript code ready to save as {page_name}.tsx"""
        
        page_code = await temp_client.create(
            messages=[
                {"role": "system", "content": assembly_system_prompt},
                {"role": "user", "content": assembly_user_prompt}
            ]
        )
        
        # 清理可能的 markdown 代码块标记
        page_code = page_code.strip()
        
        # 移除开头的 markdown 代码块标记
        if page_code.startswith("```"):
            lines = page_code.split('\n')
            # 移除第一行（可能是 ```typescript, ```tsx, 或只是 ```）
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 移除最后一行（如果是 ```）
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            page_code = '\n'.join(lines).strip()
        
        # 验证并确保导出组件名与 page_name 相同
        page_code = self._ensure_correct_export_name(page_code, page_name)
        
        return {
            "page_code": page_code,
            "page_description": f"Complete React page for {page_name}",
            "assembly_notes": f"Page assembled from root component with layout description and child page integration. Exported as {page_name}."
        }
    
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
    
    def _load_control_json(self, control_json_path: str) -> Dict[str, Any]:
        """加载 control JSON 文件"""
        path = Path(control_json_path)
        
        if not path.exists():
            raise FileNotFoundError(f"control JSON 文件不存在: {control_json_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _merge_child_react_code(self, child_results: List[Dict[str, Any]]) -> str:
        """合并子组件的 React 代码"""
        if not child_results:
            return ""
        
        merged_code = []
        
        for child in child_results:
            component_name = child.get("component_name", "Unknown")
            react_code = child.get("react_code", "")
            
            merged_code.append(f"// Child Component: {component_name}")
            merged_code.append(react_code)
            merged_code.append("")
        
        return "\n".join(merged_code)
    
    def _format_typescript_code(self, code: str) -> str:
        """
        格式化 TypeScript 代码
        
        Args:
            code: 原始代码
            
        Returns:
            格式化后的代码
        """
        import re
        
        # 如果代码已经有合理的换行（多于5行），则认为已格式化，直接返回
        lines = code.split('\n')
        if len(lines) > 5:
            return code
        
        # 否则，对压缩的单行代码进行格式化
        # 在 { 后添加换行
        code = re.sub(r'\{\s*', '{\n', code)
        
        # 在 ; 后添加换行（但不包括 for 循环中的分号）
        code = re.sub(r';(?!\s*\))', ';\n', code)
        
        # 在 } 前后添加换行
        code = re.sub(r'\s*\}', '\n}', code)
        code = re.sub(r'\}(?!\s*[,;)\]])', '}\n', code)
        
        # 在 TSX 标签间添加换行
        code = re.sub(r'>(?=<[A-Z])', '>\n', code)  # 组件标签
        code = re.sub(r'>(?=<[a-z])', '>\n', code)  # HTML 标签
        
        # 在箭头函数的 => 后添加换行
        code = re.sub(r'=>\s*\{', '=> {\n', code)
        
        # 清理多余的空行
        code = re.sub(r'\n\s*\n\s*\n+', '\n\n', code)
        
        # 基本的缩进（简单实现）
        lines = code.split('\n')
        indented_lines = []
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                indented_lines.append('')
                continue
            
            # 减少缩进（在 } 行）
            if stripped.startswith('}') or stripped.startswith(']') or stripped.startswith(')'):
                indent_level = max(0, indent_level - 1)
            
            # 添加缩进
            indented_lines.append('  ' * indent_level + stripped)
            
            # 增加缩进（在 { 后）
            if stripped.endswith('{') or stripped.endswith('[') or stripped.endswith('('):
                indent_level += 1
            # 特殊情况：行包含 { 和 }，但 { 更多
            elif stripped.count('{') > stripped.count('}'):
                indent_level += stripped.count('{') - stripped.count('}')
            elif stripped.count('}') > stripped.count('{'):
                pass  # 已经在前面处理过了
        
        return '\n'.join(indented_lines)
    
    def _generate_complete_tsx_file(
        self,
        root_component: Dict[str, Any],
        output_path: Path
    ):
        """
        生成完整的 TSX 文件
        
        注意：页面整合后，react_code 已经是完整的页面代码，直接写入即可。
        
        Args:
            root_component: 根组件的迁移结果
            output_path: 输出文件路径
        """
        react_code = root_component.get("react_code", "")
        
        if not react_code:
            self.logger.warning("react_code 为空，无法生成文件")
            return
        
        # 直接写入完整的页面代码（已经过页面整合阶段处理）
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(react_code)
    
    def _generate_output(
        self,
        page_name: str,
        result: Dict[str, Any],
        output_dir: Optional[str] = None
    ) -> str:
        """
        生成输出文件
        
        Args:
            page_name: 页面名称
            result: 迁移结果
            output_dir: 输出目录（如果为 None 则使用默认目录，仅用于 JSON 文件）
        
        Returns:
            JSON 文件路径
        """
        # 确定 JSON 文件输出目录（实验记录）
        if output_dir:
            json_dir = Path(output_dir)
        else:
            json_dir = self.migration_dir
        
        json_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成 JSON 文件（完整的迁移结果，存储在 outputs/{repo}/migration/）
        json_path = json_dir / f"{page_name}_migration.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"✓ 保存完整迁移结果（JSON）: {json_path}")
        
        # 生成完整的 TSX 文件（最终迁移结果，存储在 result/{repo}/）
        result_dir = self.result_dir
        result_dir.mkdir(parents=True, exist_ok=True)
        
        tsx_path = result_dir / f"{page_name}.tsx"
        root_component = result.get("root_component", {})
        
        if root_component:
            self._generate_complete_tsx_file(root_component, tsx_path)
            self.logger.info(f"✓ 保存 TypeScript 组件文件（TSX）: {tsx_path}")
        else:
            self.logger.warning("未找到根组件数据，跳过 TSX 文件生成")
        
        return str(json_path)
