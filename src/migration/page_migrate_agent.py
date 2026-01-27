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
    5. 通过消息传递协调 PageAssemblyAgent 进行页面整合
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
    
        # 数据描述文件路径
        self.data_descriptions_file = self.migration_dir / "data_descriptions.json"
        self._data_descriptions_cache: Optional[Dict[str, Any]] = None  # 缓存数据描述信息
    
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
        
        # 3. 提取根节点的 template 和 data 信息
        root_info = control_data.get("root_info", {})
        root_template = root_info.get("template", "")
        root_data = root_info.get("data", {})
        
        # 如果存在数据资源，从 data_descriptions.json 中获取迁移后的信息
        migrated_data_info = {}
        if root_data and root_data.get("key"):
            data_key = root_data.get("key")
            migrated_data_info = self._get_migrated_data_info(data_key)
        
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
            ctx=ctx
        )
        
        # 日志：组件迁移完成
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"组件迁移完成: {page_name}")
        self.logger.debug(f"  已迁移组件数: {len(self.migration_cache)}")
        self.logger.debug(f"  根组件: {root_result.get('component_name', 'Unknown')}")
        self.logger.info(f"{'='*80}\n")
        
        # 4. 页面整合阶段：通过消息传递请求 PageAssemblyAgent 整合页面
        self.logger.info("开始页面整合...")
        page_source = tree.get("source_code", "")
        
        # 第一阶段：获取直接依赖页面和 C# 文件路径（用于布局分析）
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
        direct_dependencies = page_info.get('dependencies', [])
        cs_file_path = page_info.get('cs_file', '')
        
        # 第二阶段：分析页面布局和子页面引用位置
        from src.llm import LLMClient, LLMConfig
        temp_config = LLMConfig(
            model=self.llm_client.config.model,
            temperature=self.llm_client.config.temperature,
            json_mode=False
        )
        temp_client = LLMClient(config=temp_config)
        
        # 读取 C# 文件内容
        cs_source_code = ""
        if cs_file_path:
            cs_path = Path(cs_file_path)
            if cs_path.exists():
                try:
                    with open(cs_path, 'r', encoding='utf-8') as f:
                        cs_source_code = f.read()
                except UnicodeDecodeError:
                    with open(cs_path, 'r', encoding='latin-1') as f:
                        cs_source_code = f.read()
        
        # 分析布局和子页面引用
        layout_system_prompt = """You are an expert in UI/UX analysis and code analysis.

Your task: Analyze the WPF page source code (XAML) and C# code-behind file to:
1. Describe the overall layout structure in natural language
2. Identify where dependent child pages are referenced and used

## Output Format:

[Layout Description]
[Your layout description here]
[/Layout Description]

[Child Page References]
[Your analysis of child page references here. If no child pages are referenced, state "No child pages are referenced in this page."]
[/Child Page References]

Output ONLY the analysis text, no code, no markdown formatting, no explanations."""
        
        layout_user_prompt = f"""Analyze this WPF page:

[XAML Source Code]
{page_source}
[/XAML Source Code]

[C# Code-Behind]
{cs_source_code if cs_source_code else "(C# file not found or empty)"}
[/C# Code-Behind]

[Direct Dependencies]
{', '.join(direct_dependencies) if direct_dependencies else 'None'}
[/Direct Dependencies]"""
        
        layout_analysis = await temp_client.create(
            messages=[
                {"role": "system", "content": layout_system_prompt},
                {"role": "user", "content": layout_user_prompt}
            ]
        )
        
        # 解析布局描述和子页面引用说明
        layout_analysis = layout_analysis.strip()
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
            page_layout_description = layout_analysis
        
        if not page_layout_description:
            page_layout_description = "Standard page layout structure."
        if not child_page_references:
            child_page_references = "No child pages are referenced in this page."
        
        # 第三阶段：通过消息传递请求 PageAssemblyAgent 整合页面
        # 如果存在迁移后的数据信息，使用迁移后的信息；否则使用原始数据资源
        data_to_pass = migrated_data_info if migrated_data_info else (root_data if root_data else {})
        
        assembly_request = PageAssemblyRequest(
            page_name=page_name,
            page_source=page_source,
            page_layout_description=page_layout_description,
            child_page_references=child_page_references,
            direct_dependencies=direct_dependencies,
            root_component=root_result.get("react_code", ""),
            root_component_name=root_result.get("component_name", ""),
            root_imports=root_result.get("imports", []),
            root_interfaces=root_result.get("interfaces", ""),
            template=root_template,
            data=data_to_pass
        )
        
        # 发送消息到 PageAssemblyAgent
        assembly_response: PageAssemblyResponse = await self.send_message(
            message=assembly_request,
            recipient=AgentId(type="PageAssemblyAgent", key="default"),
            cancellation_token=ctx.cancellation_token
        )
        
        # 用整合后的页面代码替换根组件的 react_code
        root_result["react_code"] = assembly_response.page_code
        root_result["description"] = assembly_response.page_description
        root_result["migration_notes"] = assembly_response.assembly_notes
        
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
        ctx: MessageContext
    ) -> Dict[str, Any]:
        """
        递归迁移节点及其子节点
        
        Args:
            node: 节点数据
            node_path: 节点路径（唯一标识）
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
        template_code = node.get("template", "")  # 依赖的模板代码（DataTemplate/ControlTemplate 等）
        data_resource = node.get("data", {})  # 依赖的数据资源（从 data_resources.json 中提取）
        children = node.get("children", [])
        
        # 如果存在数据资源，从 data_descriptions.json 中获取迁移后的信息
        migrated_data_info = {}
        if data_resource and data_resource.get("key"):
            data_key = data_resource.get("key")
            migrated_data_info = self._get_migrated_data_info(data_key)
        
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
        mui_response: MUISelectionResponse = await self.send_message(
            message=mui_request,
            recipient=AgentId(type="MUISelectAgent", key="default"),
            cancellation_token=ctx.cancellation_token
        )
        
        # 显示选择的 MUI 组件
        mui_components_str = ', '.join(mui_response.selected_components) if mui_response.selected_components else '(无)'
        self.logger.debug(f"{indent}  MUI: [{mui_components_str}]")
        
        # 4. 构建 MUI 组件名和使用示例的配对列表
        mui_components_docs = []
        for component_name, usage_example in zip(mui_response.selected_components, mui_response.docs):
            mui_components_docs.append(f"[{component_name}]\n{usage_example}\n[/{component_name}]")
        mui_components_docs_str = "\n\n".join(mui_components_docs)
        
        # 5. 通过消息传递请求 ComponentMigrateAgent 迁移组件
        # 如果存在迁移后的数据信息，使用迁移后的信息；否则使用原始数据资源
        data_to_pass = migrated_data_info if migrated_data_info else (data_resource if data_resource else {})
        
        migrate_request = ComponentMigrationRequest(
            wpf_source=xaml_code,
            child_react_code=child_react_code,
            mui_components_docs=mui_components_docs_str,
            template=template_code,
            data=data_to_pass
        )
        
        # 发送消息到 ComponentMigrateAgent
        migrate_response: ComponentMigrationResponse = await self.send_message(
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
    
    def _load_data_descriptions(self) -> Dict[str, Any]:
        """
        加载数据描述文件（data_descriptions.json）
        
        Returns:
            数据描述字典，格式: {key: {ts_code: str, import_statement: str}}
        """
        if self._data_descriptions_cache is not None:
            return self._data_descriptions_cache
        
        if not self.data_descriptions_file.exists():
            self.logger.debug(f"数据描述文件不存在: {self.data_descriptions_file}")
            self._data_descriptions_cache = {}
            return {}
        
        try:
            with open(self.data_descriptions_file, 'r', encoding='utf-8') as f:
                self._data_descriptions_cache = json.load(f)
            self.logger.debug(f"已加载数据描述文件: {self.data_descriptions_file}")
            return self._data_descriptions_cache
        except Exception as e:
            self.logger.warning(f"加载数据描述文件失败: {self.data_descriptions_file} - {e}")
            self._data_descriptions_cache = {}
            return {}
    
    def _get_migrated_data_info(self, data_key: str) -> Dict[str, Any]:
        """
        根据数据资源的 key 获取迁移后的信息
        
        Args:
            data_key: 数据资源的 key（如 "ExpenseData", "CostCenters"）
            
        Returns:
            迁移后的数据信息字典，格式: {ts_code: str, import_statement: str}
            如果未找到，返回空字典
        """
        data_descriptions = self._load_data_descriptions()
        return data_descriptions.get(data_key, {})
    
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
        
        # 移除可能的代码标记（确保代码干净）
        import re
        if "[TypeScript Code]" in react_code or "[/TypeScript Code]" in react_code:
            react_code = re.sub(r'^\s*\[TypeScript\s+Code\]\s*\n?', '', react_code, flags=re.IGNORECASE | re.MULTILINE)
            react_code = re.sub(r'\n?\s*\[/TypeScript\s+Code\]\s*$', '', react_code, flags=re.IGNORECASE | re.MULTILINE)
            react_code = react_code.strip()
        
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
