"""
控件依赖关系识别模块
用于从 XAML JSON 文件中提取 WPF 基础控件及其层级结构
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.common.logging import get_logger
from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    SourceIdentityError,
    artifact_source_id,
    control_json_path,
    normalize_page_id,
)
from src.parser.io_utils import read_json, write_json
from .wpf_base_controls import WPF_BASE_CONTROLS, is_wpf_base_control


class ControlDependencyAnalyzer:
    """控件依赖关系分析器"""

    _NON_VISUAL_CUSTOM_SUFFIXES = (
        'action',
        'behavior',
        'collection',
        'command',
        'converter',
        'extension',
        'preset',
        'provider',
        'service',
        'transition',
        'trigger',
        'validator',
        'viewmodel',
    )
    
    def __init__(self, output_base_dir: str = "outputs"):
        """
        初始化分析器
        
        Args:
            output_base_dir: 输出基础目录（默认为 "outputs"）
        """
        self.output_base_dir = Path(output_base_dir)
        self.control_dependencies: Dict[str, Dict[str, Any]] = {}  # {文件名: 控件依赖信息}
        self.template_resources: Dict[str, Any] = {}  # 模板资源字典，从 template_resources.json 加载
        self.data_resources: Dict[str, Dict[str, Any]] = {}  # 数据资源字典，从 data_resources.json 加载，key 为数据资源的 key
        
        # 初始化日志
        self.logger = get_logger("control_dependency")
    
    def _load_template_resources(self, project_name: str) -> None:
        """
        加载模板资源文件
        
        Args:
            project_name: 项目名称
        """
        # 加载模板资源
        template_resources_path = self.output_base_dir / project_name / "dependency" / "template_resources.json"
        
        if template_resources_path.exists():
            try:
                with open(template_resources_path, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    self.template_resources = template_data.get('templates_by_key', {})
                    self.logger.debug(f"已加载 {len(self.template_resources)} 个模板资源")
            except Exception as e:
                self.logger.warning(f"加载模板资源文件失败: {e}")
                self.template_resources = {}
        else:
            self.logger.debug(f"模板资源文件不存在: {template_resources_path}")
            self.template_resources = {}
    
    def _load_data_resources(self, project_name: str) -> None:
        """
        加载数据资源文件
        
        Args:
            project_name: 项目名称
        """
        # 加载数据资源
        data_resources_path = self.output_base_dir / project_name / "dependency" / "data_resources.json"
        
        if data_resources_path.exists():
            try:
                with open(data_resources_path, 'r', encoding='utf-8') as f:
                    data_data = json.load(f)
                    data_resources_list = data_data.get('data_resources', [])
                    
                    # 构建以 key 为键的字典
                    self.data_resources = {}
                    for resource in data_resources_list:
                        key = resource.get('key', '')
                        if key:
                            self.data_resources[key] = resource
                    
                    self.logger.debug(f"已加载 {len(self.data_resources)} 个数据资源")
            except Exception as e:
                self.logger.warning(f"加载数据资源文件失败: {e}")
                self.data_resources = {}
        else:
            self.logger.debug(f"数据资源文件不存在: {data_resources_path}")
            self.data_resources = {}
    
    def _find_template_in_style(self, style_key: str) -> Optional[str]:
        """
        通过 Style key 查找引用的模板资源
        
        直接通过 Style key 在 templates_by_key 中查找，因为 Style key 已经作为 key 存在于 templates_by_key 中
        
        Args:
            style_key: Style 资源的 key（例如 "ExpenseChart"）
            
        Returns:
            如果找到模板资源，返回模板的 source_code；否则返回 None
        """
        # 直接在 templates_by_key 中查找 Style key
        template_list = self.template_resources.get(style_key, [])
        if not template_list or len(template_list) == 0:
            return None
        
        template_source_code = template_list[0].get('source_code', '')
        return template_source_code if template_source_code else None
    
    def _find_template_in_control(self, attributes: Dict[str, Any]) -> Optional[str]:
        """
        在控件的属性中查找模板资源引用
        
        只检查控件的直接属性（attributes），不检查 source_code，
        因为 source_code 可能包含子组件的代码，导致父组件被误判为使用了模板。
        
        Args:
            attributes: 控件的属性字典
            
        Returns:
            如果找到模板资源，返回模板的 source_code；否则返回 None
        """
        if not self.template_resources:
            return None
        
        # 检查所有可用的模板 key
        for template_key, template_list in self.template_resources.items():
            if not template_list or len(template_list) == 0:
                continue
            
            # 获取第一个模板的 source_code（通常每个 key 只有一个模板）
            template_source_code = template_list[0].get('source_code', '')
            if not template_source_code:
                continue
            
            # 只检查 attributes 中是否包含模板引用
            # 常见的模板属性：ItemTemplate, ContentTemplate, Template, HeaderTemplate 等
            template_attributes = [
                'ItemTemplate', 'ContentTemplate', 'Template', 
                'HeaderTemplate', 'CellTemplate', 'ColumnHeaderTemplate', 
                'RowHeaderTemplate', 'ItemContainerTemplate'
            ]
            
            for attr_name in template_attributes:
                attr_value = attributes.get(attr_name, '')
                if isinstance(attr_value, str):
                    # 检查是否包含 {StaticResource TemplateKey} 或 {DynamicResource TemplateKey}
                    static_pattern = rf'{{StaticResource\s+{re.escape(template_key)}}}'
                    dynamic_pattern = rf'{{DynamicResource\s+{re.escape(template_key)}}}'
                    
                    if re.search(static_pattern, attr_value, re.IGNORECASE) or \
                       re.search(dynamic_pattern, attr_value, re.IGNORECASE):
                        return template_source_code
        
        return None
    
    def _find_template_in_non_control(self, node: Dict[str, Any]) -> Optional[str]:
        """
        在非基础控件节点中查找模板资源引用（通过 Style 属性）
        
        如果非基础控件通过 Style 引用了模板资源，返回模板的 source_code
        
        Args:
            node: XAML 节点
            
        Returns:
            如果找到模板资源，返回模板的 source_code；否则返回 None
        """
        attributes = node.get('attributes', {})
        style_value = attributes.get('Style', '')
        
        if not isinstance(style_value, str):
            return None
        
        # 提取 Style 的 key（例如从 "{StaticResource ExpenseChart}" 中提取 "ExpenseChart"）
        static_match = re.search(r'\{StaticResource\s+(\w+)\}', style_value, re.IGNORECASE)
        dynamic_match = re.search(r'\{DynamicResource\s+(\w+)\}', style_value, re.IGNORECASE)
        
        style_key = None
        if static_match:
            style_key = static_match.group(1)
        elif dynamic_match:
            style_key = dynamic_match.group(1)
        
        if style_key:
            # 在 Style 资源中查找引用的模板
            return self._find_template_in_style(style_key)
        
        return None
    
    def _find_data_in_control(self, attributes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        在控件的属性中查找数据资源引用
        
        只检查控件的直接属性（attributes），不检查 source_code，
        因为 source_code 可能包含子组件的代码，导致父组件被误判为使用了数据资源。
        
        Args:
            attributes: 控件的属性字典
            
        Returns:
            如果找到数据资源，返回数据资源字典；否则返回 None
        """
        if not self.data_resources:
            return None
        
        # 检查所有属性值中是否包含数据资源引用
        # 常见的数据绑定属性：ItemsSource, Source, DataContext 等
        for attr_name, attr_value in attributes.items():
            if not isinstance(attr_value, str):
                continue
            
            # 检查是否包含 {StaticResource Key} 或 {DynamicResource Key} 或 {Binding Source={StaticResource Key}}
            # 匹配模式：{StaticResource Key} 或 {DynamicResource Key} 或 {Binding Source={StaticResource Key}}
            for data_key in self.data_resources.keys():
                # 模式1: {StaticResource Key} 或 {DynamicResource Key}
                static_pattern = rf'{{StaticResource\s+{re.escape(data_key)}}}'
                dynamic_pattern = rf'{{DynamicResource\s+{re.escape(data_key)}}}'
                
                # 模式2: {Binding Source={StaticResource Key}} 或 {Binding Source={DynamicResource Key}}
                binding_static_pattern = rf'{{Binding\s+Source\s*=\s*{{StaticResource\s+{re.escape(data_key)}}}}}'
                binding_dynamic_pattern = rf'{{Binding\s+Source\s*=\s*{{DynamicResource\s+{re.escape(data_key)}}}}}'
                
                if (re.search(static_pattern, attr_value, re.IGNORECASE) or
                    re.search(dynamic_pattern, attr_value, re.IGNORECASE) or
                    re.search(binding_static_pattern, attr_value, re.IGNORECASE) or
                    re.search(binding_dynamic_pattern, attr_value, re.IGNORECASE)):
                    return self.data_resources[data_key]
        
        return None
    
    def _find_data_in_non_control(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        在非基础控件节点中查找数据资源引用（通过属性）
        
        如果非基础控件通过属性引用了数据资源，返回数据资源字典
        
        Args:
            node: XAML 节点
            
        Returns:
            如果找到数据资源，返回数据资源字典；否则返回 None
        """
        if not self.data_resources:
            return None
        
        attributes = node.get('attributes', {})
        
        # 检查所有属性值中是否包含数据资源引用
        for attr_name, attr_value in attributes.items():
            if not isinstance(attr_value, str):
                continue
            
            # 检查是否包含数据资源引用
            for data_key in self.data_resources.keys():
                # 模式1: {StaticResource Key} 或 {DynamicResource Key}
                static_pattern = rf'{{StaticResource\s+{re.escape(data_key)}}}'
                dynamic_pattern = rf'{{DynamicResource\s+{re.escape(data_key)}}}'
                
                # 模式2: {Binding Source={StaticResource Key}} 或 {Binding Source={DynamicResource Key}}
                binding_static_pattern = rf'{{Binding\s+Source\s*=\s*{{StaticResource\s+{re.escape(data_key)}}}}}'
                binding_dynamic_pattern = rf'{{Binding\s+Source\s*=\s*{{DynamicResource\s+{re.escape(data_key)}}}}}'
                
                if (re.search(static_pattern, attr_value, re.IGNORECASE) or
                    re.search(dynamic_pattern, attr_value, re.IGNORECASE) or
                    re.search(binding_static_pattern, attr_value, re.IGNORECASE) or
                    re.search(binding_dynamic_pattern, attr_value, re.IGNORECASE)):
                    return self.data_resources[data_key]
        
        return None
    
    @classmethod
    def _is_migratable_custom_control(cls, node: Dict[str, Any]) -> bool:
        """过滤行为、转换器等非可视对象，只让可视自建控件进入迁移树。"""
        tag = str(node.get('tag', '')).lower()
        return (
            node.get('classification') == 'custom_control'
            and not tag.endswith(cls._NON_VISUAL_CUSTOM_SUFFIXES)
        )

    def extract_controls_from_node(
        self,
        node: Dict[str, Any],
        parent_tag: str = '',
        *,
        include_custom_controls: bool = False,
    ) -> Optional[Dict[str, Any] | List[Dict[str, Any]]]:
        """
        从节点中提取控件信息（递归）
        
        默认只保留 WPF 基础控件；迁移树还会保留可视自建控件。
        非控件容器节点会被移除，其子节点会向上提升
        忽略 *.Resources 节点中的所有内容
        
        Args:
            node: XAML 节点
            parent_tag: 父节点的 tag（用于判断是否在 Resources 中）
            
        Returns:
            如果是控件节点，返回控件信息；如果不是控件但有控件子节点，返回子节点列表；否则返回 None
        """
        if not node:
            return None
        
        tag = node.get('tag', '')
        
        # 忽略 *.Resources 节点及其所有子节点
        if tag.endswith('.Resources'):
            return None
        
        # 兼容统计树只包含基础控件；迁移树额外包含可视自建控件。
        is_control = is_wpf_base_control(tag) or (
            include_custom_controls and self._is_migratable_custom_control(node)
        )
        
        # 递归处理子节点，收集所有控件子节点
        control_children = []
        non_control_template = None  # 仅用于收集非基础控件通过 Style 引用的模板
        non_control_data = None  # 仅用于收集非基础控件引用的数据资源
        
        for child in node.get('children', []):
            child_tag = child.get('tag', '')
            child_is_control = is_wpf_base_control(child_tag) or (
                include_custom_controls
                and self._is_migratable_custom_control(child)
            )
            
            # 如果子节点不是基础控件，检查它是否通过 Style 引用了模板
            # 这种情况下的模板需要传递给父基础控件
            if not child_is_control:
                found_template = self._find_template_in_non_control(child)
                if found_template and not non_control_template:
                    non_control_template = found_template
                
                # 检查非基础控件是否引用了数据资源
                found_data = self._find_data_in_non_control(child)
                if found_data and not non_control_data:
                    non_control_data = found_data
            
            # 递归处理子节点
            extracted = self.extract_controls_from_node(
                child,
                parent_tag=tag,
                include_custom_controls=include_custom_controls,
            )
            if extracted:
                # 如果返回的是列表（子节点提升），展开添加
                if isinstance(extracted, list):
                    control_children.extend(extracted)
                else:
                    control_children.append(extracted)
        
        # 如果当前节点是控件，保留此节点
        if is_control:
            # 查找模板资源引用（只检查直接属性，不检查 source_code）
            source_code = node.get('source_code', '')
            attributes = node.get('attributes', {})
            template_source_code = self._find_template_in_control(attributes)
            
            # 只有当当前控件没有直接使用模板，且子节点中有非基础控件通过 Style 引用了模板时，
            # 才将模板传递给父控件
            # 注意：子基础控件直接使用的模板不应该传递给父控件
            # 只有当子节点是非基础控件且通过 Style 引用模板时，才传递
            if not template_source_code and non_control_template:
                template_source_code = non_control_template
            
            # 查找数据资源引用（只检查直接属性，不检查 source_code）
            data_resource = self._find_data_in_control(attributes)
            
            # 只有当当前控件没有直接使用数据资源，且子节点中有非基础控件引用了数据资源时，
            # 才将数据资源传递给父控件
            # 注意：子基础控件直接使用的数据资源不应该传递给父控件
            # 只有当子节点是非基础控件且引用了数据资源时，才传递
            if not data_resource and non_control_data:
                data_resource = non_control_data
            
            # 确保模板和数据资源只在当前控件直接使用或非基础控件子节点引用时才设置
            # 子基础控件直接使用的模板和数据资源不应该出现在父控件中
            
            result = {
                'tag': tag,
                'node_path': node.get('node_path', ''),
                'source_line': node.get('source_line'),
                'classification': node.get('classification', 'base_control'),
                'semantic_references': node.get('semantic_references', []),
                'source_code': source_code,
                'attributes': attributes,
                'template': template_source_code if template_source_code else '',  # 模板字段，如果找到模板则填充
                'data': data_resource if data_resource else {},  # 数据字段，如果找到数据资源则填充
                'children': control_children
            }
            return result
        
        # 如果当前节点不是控件，但有控件子节点，则提升子节点
        elif control_children:
            # 如果只有一个子节点，直接返回该节点
            if len(control_children) == 1:
                return control_children[0]
            # 如果有多个子节点，返回列表让父节点展开
            else:
                return control_children
        
        return None

    @staticmethod
    def _normalize_control_tree(
        controls_root: Optional[Dict[str, Any] | List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """把提升出的多个根节点归一为迁移所需的单根树。"""
        if isinstance(controls_root, list):
            if len(controls_root) == 1:
                return controls_root[0]
            first_tag = controls_root[0].get('tag', 'Root') if controls_root else 'Root'
            return {
                'tag': first_tag,
                'source_code': '',
                'attributes': {},
                'template': '',
                'data': {},
                'children': controls_root,
            }
        if controls_root is not None:
            return controls_root
        return {
            'tag': 'Root',
            'source_code': '',
            'attributes': {},
            'template': '',
            'data': {},
            'children': [],
        }

    def _build_node_inventory(
        self,
        root: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """保留完整节点角色清单，避免非基础节点在控件树外静默消失。"""
        inventory: List[Dict[str, Any]] = []

        def visit(node: Dict[str, Any], *, under_resources: bool = False) -> None:
            tag = str(node.get('tag', ''))
            classification = str(
                node.get('classification')
                or ('base_control' if is_wpf_base_control(tag) else 'unsupported_node')
            )
            node_path = str(node.get('node_path', ''))
            in_resources = under_resources or tag.endswith('.Resources')
            if classification == 'page_or_document_root':
                retention = 'root_info'
                reason = '页面或文档根节点由 root_info 单独保留'
            elif is_wpf_base_control(tag) and not in_resources:
                retention = 'control_tree'
                reason = '进入兼容的基础控件树'
            else:
                retention = 'separate_inventory'
                reason = (
                    '资源子树不参与逐控件迁移'
                    if in_resources or classification == 'resource_node'
                    else '非基础控件节点保留在完整分类清单中'
                )
            inventory.append(
                {
                    'node_path': node_path,
                    'source_line': node.get('source_line'),
                    'tag': tag,
                    'full_tag': node.get('full_tag', tag),
                    'namespace': node.get('namespace'),
                    'classification': classification,
                    'classification_reason': node.get(
                        'classification_reason', ''
                    ),
                    'retention': retention,
                    'retention_reason': reason,
                    'attributes': node.get('attributes', {}),
                    'attribute_details': node.get('attribute_details', []),
                    'semantic_references': node.get('semantic_references', []),
                }
            )
            for child in node.get('children', []):
                if isinstance(child, dict):
                    visit(child, under_resources=in_resources)

        if root:
            visit(root)
        return sorted(inventory, key=lambda item: item['node_path'])
    
    def analyze_xaml_file(self, xaml_json_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        """
        分析单个 XAML JSON 文件，提取控件依赖
        
        Args:
            xaml_json_path: XAML JSON 文件路径
            project_name: 项目名称（用于加载模板资源，如果为 None 则从路径推断）
            
        Returns:
            控件依赖信息字典
        """
        # 如果提供了 project_name 且模板资源未加载，则加载模板资源
        if project_name and not self.template_resources:
            self._load_template_resources(project_name)
        
        # 如果提供了 project_name 且数据资源未加载，则加载数据资源
        if project_name and not self.data_resources:
            self._load_data_resources(project_name)
        
        # 读取 XAML JSON 文件
        xaml_data = read_json(xaml_json_path)
        
        # 提取基本信息
        source_file = xaml_data.get('source_file', '')
        page_id = normalize_page_id(artifact_source_id(xaml_data, xaml_json_path))
        namespaces = xaml_data.get('namespaces', {})
        root = xaml_data.get('root', {})
        root_tag = root.get('tag', 'Root')  # 获取根节点的 tag
        
        # 提取根节点的资源信息（template 和 data）
        root_attributes = root.get('attributes', {})
        root_source_code = root.get('source_code', '')
        root_template_source_code = self._find_template_in_control(root_attributes)
        root_data_resource = self._find_data_in_control(root_attributes)
        node_inventory = self._build_node_inventory(root)
        classification_summary: Dict[str, int] = {}
        for item in node_inventory:
            classification = item['classification']
            classification_summary[classification] = (
                classification_summary.get(classification, 0) + 1
            )
        
        # 构建根节点信息
        root_info = {
            'tag': root_tag,
            'source_code': root_source_code,
            'attributes': root_attributes,
            'node_path': root.get('node_path', ''),
            'source_line': root.get('source_line'),
            'classification': root.get('classification', ''),
            'semantic_references': root.get('semantic_references', []),
            'template': root_template_source_code if root_template_source_code else '',
            'data': root_data_resource if root_data_resource else {}
        }
        
        # 提取控件信息（从根节点开始提取，但根节点本身不会被包含在结果中）
        controls_root = self._normalize_control_tree(
            self.extract_controls_from_node(root)
        )
        migration_controls_root = self._normalize_control_tree(
            self.extract_controls_from_node(root, include_custom_controls=True)
        )
        
        # 统计控件数量
        control_count = self._count_controls(controls_root)
        migration_control_count = self._count_controls(migration_controls_root)
        
        # 构建结果
        result = {
            'id_scheme': SOURCE_ID_SCHEME,
            'page_id': page_id,
            'source_id': page_id,
            'source_file': source_file,
            'xaml_json_file': xaml_json_path,
            'namespaces': namespaces,
            'control_count': control_count,
            'migration_control_count': migration_control_count,
            'node_inventory_count': len(node_inventory),
            'node_classification_summary': dict(
                sorted(classification_summary.items())
            ),
            'node_inventory': node_inventory,
            'custom_controls': [
                item
                for item in node_inventory
                if item['classification'] == 'custom_control'
            ],
            'unsupported_nodes': [
                item
                for item in node_inventory
                if item['classification'] == 'unsupported_node'
            ],
            'root_info': root_info,  # 根节点信息，与 controls 平级
            'controls': controls_root,  # 只包含基础控件树，保持冻结评测口径
            'migration_controls': migration_controls_root,
        }
        
        return result
    
    def _count_controls(self, node: Optional[Dict[str, Any]]) -> int:
        """
        递归统计控件数量
        
        Args:
            node: 节点（所有节点都是控件）
            
        Returns:
            控件数量
        """
        if not node:
            return 0
        
        # 所有保留的节点都是控件，计数为 1
        count = 1
        
        # 递归统计子节点
        for child in node.get('children', []):
            count += self._count_controls(child)
        
        return count
    
    def save_to_json(self, xaml_filename: str, project_name: str, 
                    output_dir: Optional[str] = None) -> str:
        """
        保存控件依赖信息为 JSON 文件
        
        Args:
            xaml_filename: 页面 ID（如 "Views/MainWindow.xaml"）
            project_name: 项目名称
            output_dir: 输出目录（如果为 None，则使用 outputs/{project_name}/dependency）
            
        Returns:
            输出文件的完整路径
        """
        if output_dir is None:
            output_dir = self.output_base_dir / project_name / "dependency"
        else:
            output_dir = Path(output_dir)
        
        page_id = normalize_page_id(xaml_filename)
        output_file = control_json_path(output_dir, page_id)
        
        # 获取控件依赖信息
        if page_id not in self.control_dependencies:
            raise ValueError(f"未找到页面 {page_id} 的控件依赖信息")

        write_json(output_file, self.control_dependencies[page_id])
        
        return str(output_file)
    
    def analyze_project(self, project_name: str, 
                       output_base_dir: str = "outputs") -> Dict[str, str]:
        """
        分析项目中所有 XAML 文件的控件依赖
        
        只处理 type=page 的 XAML 文件，跳过 type=root 和 type=else 的文件
        
        Args:
            project_name: 项目名称
            output_base_dir: 输出基础目录
            
        Returns:
            字典，键为 XAML 文件名，值为输出文件路径
        """
        # 查找 XAML JSON 文件目录
        xaml_json_dir = Path(output_base_dir) / project_name / "xaml"
        
        if not xaml_json_dir.exists():
            raise FileNotFoundError(f"未找到项目 {project_name} 的 XAML JSON 目录: {xaml_json_dir}")
        
        # 初始化日志
        logger = get_logger("control_dependency")
        
        # 查找所有 XAML JSON 文件（排除 .csproj.json）
        xaml_json_files = [
            f for f in xaml_json_dir.rglob("*.xaml.json")
        ]
        
        if not xaml_json_files:
            logger.warning(f"在 {xaml_json_dir} 中未找到 XAML JSON 文件")
            return {}
        
        results = {}
        success_count = 0
        skipped_count = 0
        error_count = 0
        
        logger.info("=" * 70)
        logger.info(f"控件依赖分析 - 项目: {project_name}")
        logger.info("=" * 70)
        logger.info(f"找到 {len(xaml_json_files)} 个 XAML JSON 文件")
        logger.debug("-" * 70)
        
        # 加载模板资源和数据资源
        self._load_template_resources(project_name)
        self._load_data_resources(project_name)
        
        for xaml_json_file in xaml_json_files:
            try:
                # 读取 JSON 文件检查 type 字段
                xaml_data = read_json(xaml_json_file)
                xaml_filename = normalize_page_id(
                    artifact_source_id(xaml_data, xaml_json_file)
                )
                
                file_type = xaml_data.get('type', 'unknown')
                
                # 只处理 type=page 的文件
                if file_type != 'page':
                    skipped_count += 1
                    print(f"- {xaml_filename:40} (跳过: type={file_type})")
                    continue
                
                # 分析控件依赖
                control_dep = self.analyze_xaml_file(str(xaml_json_file), project_name=project_name)
                self.control_dependencies[xaml_filename] = control_dep
                
                # 保存结果
                output_file = self.save_to_json(xaml_filename, project_name)
                
                results[xaml_filename] = output_file
                success_count += 1
                
                # 输出信息
                control_count = control_dep.get('control_count', 0)
                logger.info(f"✓ {xaml_filename:40} -> {control_count:3} 个控件 (type=page)")
                
            except SourceIdentityError:
                raise
            except Exception as e:
                error_count += 1
                logger.error(f"✗ {xaml_json_file.name}: 分析失败 - {str(e)}")
        
        logger.debug("-" * 70)
        logger.info(f"分析完成: 成功 {success_count} 个, 跳过 {skipped_count} 个, 失败 {error_count} 个")
        logger.info(f"输出目录: {Path(output_base_dir) / project_name / 'dependency'}")
        logger.info("=" * 70)
        
        return results
    
    def print_control_tree(self, node: Optional[Dict[str, Any]], indent: int = 0):
        """
        打印控件树结构（用于调试）
        
        Args:
            node: 控件节点
            indent: 缩进级别
        """
        if not node:
            return
        
        indent_str = "  " * indent
        tag = node.get('tag', '')
        
        # 所有节点都是控件
        self.logger.debug(f"{indent_str}✓ <{tag}>")
        
        # 递归打印子节点
        for child in node.get('children', []):
            self.print_control_tree(child, indent + 1)
    
    @staticmethod
    def analyze_project_static(project_name: str, 
                               output_base_dir: str = "outputs") -> Dict[str, str]:
        """
        静态方法：分析项目控件依赖
        
        Args:
            project_name: 项目名称
            output_base_dir: 输出基础目录
            
        Returns:
            字典，键为 XAML 文件名，值为输出文件路径
        """
        analyzer = ControlDependencyAnalyzer(output_base_dir)
        return analyzer.analyze_project(project_name, output_base_dir)


# 运行示例：python -m src.parser.control_dependency
if __name__ == "__main__":
    logger = get_logger("control_dependency")
    
    # 分析项目控件依赖
    results = ControlDependencyAnalyzer.analyze_project_static("ExpenseItDemo")
    
    logger.info("\n" + "=" * 70)
    logger.info("生成的文件:")
    logger.info("=" * 70)
    for xaml_file, output_file in results.items():
        logger.info(f"  {xaml_file} -> {output_file}")
    logger.info("=" * 70)
