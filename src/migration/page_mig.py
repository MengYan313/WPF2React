# -*- coding: utf-8 -*-
"""
WPF 页面到 React 页面迁移模块

负责分析整个 XAML 页面的组件树，从叶子节点逐步向上递归迁移。
"""

import json
from typing import Dict, Optional, Any, List, Tuple
from pathlib import Path

from .component_mig import ComponentMigrator
from .mui_selector import MUIComponentSelector
from ..llm import LLMConfig


class PageMigrator:
    """
    WPF 页面迁移器
    
    负责分析 XAML 页面的组件嵌套结构，从叶子节点向上递归迁移每个组件。
    使用节点路径作为唯一标识符来存储迁移结果，避免同名组件冲突。
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None,
        component_migrator: Optional[ComponentMigrator] = None,
        mui_selector: Optional[MUIComponentSelector] = None
    ):
        """
        初始化页面迁移器
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置
            component_migrator: 组件迁移器实例（如果为 None 则创建新实例）
            mui_selector: MUI 组件选择器实例（如果为 None 则创建新实例）
        """
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        self.component_migrator = component_migrator or ComponentMigrator(llm_config)
        self.mui_selector = mui_selector or MUIComponentSelector()
        
        # 使用节点路径作为唯一标识符，避免同名组件冲突
        # 格式: "root" -> 根节点, "root.0" -> 第一个子节点, "root.0.1" -> 第一个子节点的第二个子节点
        self.migration_cache: Dict[str, Dict[str, Any]] = {}
        
        # 设置目录路径
        self.dependency_dir = self.output_base_dir / project_name / "dependency"
        self.migration_dir = self.output_base_dir / project_name / "migration"
    
    def _build_node_path(self, parent_path: str, child_index: int) -> str:
        """
        构建子节点的路径标识符
        
        Args:
            parent_path: 父节点路径
            child_index: 子节点在父节点children数组中的索引
            
        Returns:
            子节点路径字符串
        """
        return f"{parent_path}.{child_index}"
    
    async def _migrate_node_recursive(
        self,
        node: Dict[str, Any],
        node_path: str,
        wpf_dependencies: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        递归迁移单个节点及其所有子节点（从叶子向上）（异步）
        
        Args:
            node: 组件节点（包含 tag, source_code, children 等字段）
            node_path: 节点的唯一路径标识符
            wpf_dependencies: WPF 依赖代码
            
        Returns:
            迁移结果字典
        """
        # 1. 先递归迁移所有子节点（从叶子开始）
        children_results = []
        if "children" in node and node["children"]:
            for child_index, child in enumerate(node["children"]):
                child_path = self._build_node_path(node_path, child_index)
                child_result = await self._migrate_node_recursive(
                    node=child,
                    node_path=child_path,
                    wpf_dependencies=wpf_dependencies
                )
                children_results.append(child_result)
        
        # 2. 收集所有子节点的 React 代码
        children_react_code = None
        if children_results:
            children_code_parts = []
            for child_result in children_results:
                component_name = child_result.get('component_name', 'Unknown')
                react_code = child_result.get('react_code', '')
                children_code_parts.append(
                    f"// Child Component: {component_name}\n{react_code}"
                )
            children_react_code = "\n\n".join(children_code_parts)
        
        # 3. 提取当前节点的 WPF 源代码
        wpf_source = node.get('source_code', '')
        if not wpf_source:
            # 如果没有源代码，可能是特殊节点，跳过或使用 tag 作为标识
            node_tag = node.get('tag', 'Unknown')
            print(f"  ⚠ 警告: 节点 {node_path} ({node_tag}) 没有 source_code，跳过迁移")
            return {
                'component_name': node_tag,
                'react_code': f'// Skipped: {node_tag}',
                'node_path': node_path
            }
        
        # 4. 使用 MUI 选择器获取相关的 MUI 组件文档
        node_tag = node.get('tag', 'Unknown')
        print(f"  迁移节点: {node_path} ({node_tag})")
        
        mui_components_docs = await self.mui_selector.get_mui_docs_for_wpf(
            wpf_source=wpf_source,
            wpf_tag=node_tag
        )
        
        # 5. 调用 ComponentMigrator 迁移当前节点
        result = await self.component_migrator.migrate(
            wpf_source=wpf_source,
            wpf_dependencies=wpf_dependencies,
            children_react_code=children_react_code,
            mui_components_docs=mui_components_docs
        )
        
        # 6. 添加节点路径到结果中
        result['node_path'] = node_path
        result['wpf_tag'] = node_tag
        
        # 7. 缓存结果（使用路径作为唯一标识）
        self.migration_cache[node_path] = result
        
        return result
    
    async def migrate_page_from_control_json(
        self,
        control_json_path: str,
        wpf_dependencies: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从 control_*.json 文件迁移整个页面（异步）
        
        Args:
            control_json_path: control JSON 文件路径（例如 outputs/ExpenseItDemo/dependency/control_MainWindow.json）
            wpf_dependencies: WPF 依赖代码
            
        Returns:
            页面根组件的迁移结果
        """
        # 1. 加载 control JSON 文件
        control_file = Path(control_json_path)
        if not control_file.exists():
            raise FileNotFoundError(f"Control JSON file not found: {control_json_path}")
        
        print(f"\n加载文件: {control_file}")
        
        with open(control_file, 'r', encoding='utf-8') as f:
            control_data = json.load(f)
        
        # 2. 提取组件树根节点
        root_node = control_data.get('controls')
        if not root_node:
            raise ValueError(f"No 'controls' field found in control JSON: {control_json_path}")
        
        control_count = control_data.get('control_count', 0)
        print(f"组件总数: {control_count}")
        print(f"根组件: {root_node.get('tag', 'Unknown')}\n")
        
        # 3. 递归迁移整个组件树
        print("开始递归迁移...")
        result = await self._migrate_node_recursive(
            node=root_node,
            node_path="root",
            wpf_dependencies=wpf_dependencies
        )
        
        print(f"\n✓ 迁移完成! 共迁移 {len(self.migration_cache)} 个组件\n")
        
        # 4. 保存结果
        page_name = control_file.stem.replace('control_', '')  # 去除 control_ 前缀
        self.save_page_results(result, page_name, control_data)
        
        return result
    
    async def migrate_page(
        self,
        page_name: str,
        wpf_dependencies: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        根据页面名称迁移页面（自动查找 control JSON 文件）（异步）
        
        Args:
            page_name: 页面名称（例如 "MainWindow"）
            wpf_dependencies: WPF 依赖代码
            
        Returns:
            页面根组件的迁移结果
        """
        # 构建 control JSON 文件路径
        control_file = self.dependency_dir / f"control_{page_name}.json"
        
        return await self.migrate_page_from_control_json(
            control_json_path=str(control_file),
            wpf_dependencies=wpf_dependencies
        )
    
    def save_page_results(
        self,
        root_result: Dict[str, Any],
        page_name: str,
        original_control_data: Optional[Dict[str, Any]] = None
    ):
        """
        保存页面迁移结果到 outputs/{project}/migration/
        
        Args:
            root_result: 根组件迁移结果
            page_name: 页面名称
            original_control_data: 原始 control JSON 数据（用于保存元信息）
        """
        # 创建输出目录
        self.migration_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 保存主要的 TypeScript 文件
        tsx_file = self.migration_dir / f"{page_name}.tsx"
        self._save_tsx_file(root_result, tsx_file)
        print(f"✓ 保存 TypeScript 文件: {tsx_file}")
        
        # 2. 保存完整的迁移元数据（包含所有组件的迁移结果）
        metadata = {
            "page_name": page_name,
            "project_name": self.project_name,
            "root_component": root_result,
            "all_components": self.migration_cache,
            "component_count": len(self.migration_cache)
        }
        
        if original_control_data:
            metadata["source_file"] = original_control_data.get("source_file")
            metadata["original_control_count"] = original_control_data.get("control_count")
        
        metadata_file = self.migration_dir / f"{page_name}.migration.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"✓ 保存迁移元数据: {metadata_file}")
        
        # 3. 保存组件树结构（用于可视化和调试）
        tree_structure = self._build_tree_structure(root_result)
        tree_file = self.migration_dir / f"{page_name}.tree.json"
        with open(tree_file, 'w', encoding='utf-8') as f:
            json.dump(tree_structure, f, indent=2, ensure_ascii=False)
        print(f"✓ 保存组件树结构: {tree_file}")
    
    def _save_tsx_file(self, result: Dict[str, Any], output_path: Path):
        """
        保存为 TypeScript 文件
        
        Args:
            result: 迁移结果字典
            output_path: 输出文件路径
        """
        component_code_parts = []
        
        # 添加文件头注释
        component_code_parts.extend([
            "/**",
            f" * Auto-generated React component from WPF",
            f" * Original WPF component: {result.get('wpf_tag', 'Unknown')}",
            f" * Migration path: {result.get('node_path', 'Unknown')}",
            " */",
            ""
        ])
        
        # 添加导入语句
        if "imports" in result and result["imports"]:
            if isinstance(result["imports"], list):
                component_code_parts.extend(result["imports"])
            else:
                component_code_parts.append(str(result["imports"]))
            component_code_parts.append("")
        
        # 添加类型定义
        if result.get("interfaces"):
            component_code_parts.append(result["interfaces"])
            component_code_parts.append("")
        
        # 添加组件代码
        component_code_parts.append(result["react_code"])
        
        # 添加迁移说明
        if result.get("migration_notes"):
            component_code_parts.extend([
                "",
                "/**",
                " * Migration Notes:",
                f" * {result['migration_notes']}",
                " */"
            ])
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(component_code_parts))
    
    def _build_tree_structure(self, root_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建组件树结构（用于可视化）
        
        Args:
            root_result: 根组件迁移结果
            
        Returns:
            树形结构字典
        """
        def build_node_tree(node_path: str) -> Optional[Dict[str, Any]]:
            """递归构建节点树"""
            if node_path not in self.migration_cache:
                return None
            
            node_data = self.migration_cache[node_path]
            
            tree_node = {
                "path": node_path,
                "component_name": node_data.get("component_name", "Unknown"),
                "wpf_tag": node_data.get("wpf_tag", "Unknown"),
                "description": node_data.get("description", ""),
                "children": []
            }
            
            # 查找子节点
            child_index = 0
            while True:
                child_path = self._build_node_path(node_path, child_index)
                child_tree = build_node_tree(child_path)
                if child_tree is None:
                    break
                tree_node["children"].append(child_tree)
                child_index += 1
            
            return tree_node
        
        return build_node_tree("root") or {}
    
    def get_component_by_path(self, node_path: str) -> Optional[Dict[str, Any]]:
        """
        根据节点路径获取组件迁移结果
        
        Args:
            node_path: 节点路径（例如 "root.0.1"）
            
        Returns:
            组件迁移结果或 None
        """
        return self.migration_cache.get(node_path)
    
    def get_all_components(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有已迁移组件的结果
        
        Returns:
            节点路径到迁移结果的字典
        """
        return self.migration_cache.copy()
    
    def clear_cache(self):
        """清空迁移缓存"""
        self.migration_cache.clear()
