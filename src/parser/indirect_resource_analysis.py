# -*- coding: utf-8 -*-
"""
间接资源引用/依赖分析模块
用于分析 WPF 项目中的间接资源引用/依赖（Resources、ResourceDictionary 中的资源）
特别是 Template 类型的资源（DataTemplate、ControlTemplate 等）
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.logger import get_logger
from src.parser.io_utils import write_json


class LayoutResourceDependencyAnalyzer:
    """间接资源引用/依赖分析器"""
    
    # Template 类型的标签（以 Template 结尾）
    TEMPLATE_TAGS = {
        'DataTemplate',
        'ControlTemplate',
        'ItemsPanelTemplate',
        'HierarchicalDataTemplate',
        'ItemContainerTemplate',
        'ItemTemplate',
        'ContentTemplate',
        'HeaderTemplate',
        'CellTemplate',
        'ColumnHeaderTemplate',
        'RowHeaderTemplate',
    }
    
    # 标准 WPF 数据提供者标签
    DATA_PROVIDER_TAGS = {
        'XmlDataProvider',
        'ObjectDataProvider',
        'CollectionViewSource',
    }
    
    def __init__(self, output_base_dir: str = "outputs"):
        """
        初始化分析器
        
        Args:
            output_base_dir: 输出基础目录（默认为 "outputs"）
        """
        self.output_base_dir = Path(output_base_dir)
        self.resources: Dict[str, List[Dict[str, Any]]] = {}  # {项目名: [资源列表]}
        self.data_resources: Dict[str, List[Dict[str, Any]]] = {}  # {项目名: [数据资源列表]}
        self.template_resources: Dict[str, List[Dict[str, Any]]] = {}  # {项目名: [模板资源列表]}
        self.custom_class_names: set = set()  # 自定义类名集合（从 CS 依赖文件加载）
        self.cs_dependency_data: Dict[str, Any] = {}  # CS 依赖数据缓存 {项目名: 依赖数据}
        self.cs_source_cache: Dict[str, Dict[str, Any]] = {}  # CS 源代码缓存 {项目名: {类名: 源代码数据}}
        
        # 初始化日志
        self.logger = get_logger("indirect_resource_analysis")
    
    def _is_resources_node(self, tag: str) -> bool:
        """
        判断是否是 Resources 节点
        
        Args:
            tag: 标签名
            
        Returns:
            是否是 Resources 节点
        """
        return tag.endswith('.Resources') or tag == 'Resources'
    
    def _is_resource_dictionary(self, tag: str) -> bool:
        """
        判断是否是 ResourceDictionary 节点
        
        Args:
            tag: 标签名
            
        Returns:
            是否是 ResourceDictionary 节点
        """
        return tag == 'ResourceDictionary'
    
    def _is_template_tag(self, tag: str) -> bool:
        """
        判断是否是 Template 类型的标签
        
        Args:
            tag: 标签名
            
        Returns:
            是否是 Template 标签
        """
        # 检查是否以 Template 结尾
        if tag.endswith('Template'):
            return True
        
        # 检查是否在已知的 Template 标签集合中
        return tag in self.TEMPLATE_TAGS
    
    def _is_data_provider_tag(self, tag: str) -> bool:
        """
        判断是否是标准 WPF 数据提供者标签
        
        Args:
            tag: 标签名
            
        Returns:
            是否是数据提供者标签
        """
        return tag in self.DATA_PROVIDER_TAGS
    
    def _is_custom_data_object(self, tag: str) -> bool:
        """
        判断是否是自定义数据对象
        
        Args:
            tag: 标签名
            
        Returns:
            是否是自定义数据对象
        """
        return tag in self.custom_class_names
    
    def _is_data_resource(self, tag: str) -> bool:
        """
        判断是否是数据资源（数据提供者或自定义数据对象）
        
        Args:
            tag: 标签名
            
        Returns:
            是否是数据资源
        """
        return self._is_data_provider_tag(tag) or self._is_custom_data_object(tag)
    
    def _load_custom_class_names(self, project_name: str) -> None:
        """
        从 CS 依赖文件中加载自定义类名和依赖关系
        
        Args:
            project_name: 项目名称
        """
        cs_dependency_file = self.output_base_dir / project_name / "dependency" / "cs_dependency.json"
        
        if not cs_dependency_file.exists():
            self.logger.warning(f"未找到 CS 依赖文件: {cs_dependency_file}")
            return
        
        try:
            with open(cs_dependency_file, 'r', encoding='utf-8') as f:
                cs_data = json.load(f)
            
            # 缓存 CS 依赖数据
            self.cs_dependency_data[project_name] = cs_data
            
            # 从 files 中提取所有 defined_types
            files = cs_data.get('files', {})
            for file_info in files.values():
                defined_types = file_info.get('defined_types', [])
                self.custom_class_names.update(defined_types)
            
            self.logger.info(f"加载了 {len(self.custom_class_names)} 个自定义类名: {sorted(self.custom_class_names)}")
        except Exception as e:
            self.logger.error(f"加载 CS 依赖文件失败: {str(e)}")
    
    def _load_cs_source_code(self, project_name: str, class_name: str) -> Optional[Dict[str, Any]]:
        """
        加载指定类的 CS 源代码
        
        Args:
            project_name: 项目名称
            class_name: 类名
            
        Returns:
            包含源代码和依赖信息的字典，如果未找到则返回 None
        """
        # 检查缓存
        if project_name not in self.cs_source_cache:
            self.cs_source_cache[project_name] = {}
        
        if class_name in self.cs_source_cache[project_name]:
            return self.cs_source_cache[project_name][class_name]
        
        # 从 CS 依赖数据中查找类对应的文件
        if project_name not in self.cs_dependency_data:
            return None
        
        cs_dependency = self.cs_dependency_data[project_name]
        files = cs_dependency.get('files', {})
        
        # 查找包含该类的文件
        target_file_info = None
        for file_key, file_info in files.items():
            defined_types = file_info.get('defined_types', [])
            if class_name in defined_types:
                target_file_info = file_info
                break
        
        if not target_file_info:
            self.logger.warning(f"未找到类 {class_name} 对应的 CS 文件")
            return None
        
        cs_file_path = target_file_info.get('cs_file', '')
        if not cs_file_path:
            return None
        
        # 从 cs_file_path 中提取文件名（不含路径）
        cs_file_name = Path(cs_file_path).name
        
        # 读取 CS JSON 文件
        cs_json_file = self.output_base_dir / project_name / "cs" / f"{cs_file_name}.json"
        
        if not cs_json_file.exists():
            self.logger.warning(f"未找到 CS JSON 文件: {cs_json_file}")
            return None
        
        try:
            with open(cs_json_file, 'r', encoding='utf-8') as f:
                cs_json_data = json.load(f)
            
            # 查找类节点
            def find_class_node(node: Dict[str, Any], target_class: str, depth: int = 0, max_depth: int = 10) -> Optional[Dict[str, Any]]:
                """递归查找类节点"""
                if depth > max_depth:
                    return None
                
                if node.get('node_type') == 'class' and node.get('name') == target_class:
                    return node
                
                for child in node.get('children', []):
                    result = find_class_node(child, target_class, depth + 1, max_depth)
                    if result:
                        return result
                
                return None
            
            root = cs_json_data.get('root', {})
            class_node = find_class_node(root, class_name)
            
            if not class_node:
                self.logger.warning(f"在 {cs_json_file} 中未找到类 {class_name}")
                return None
            
            # 获取类的源代码（优先使用 namespace 节点的源代码，因为它包含完整的命名空间）
            namespace_node = None
            for child in root.get('children', []):
                if child.get('node_type') == 'namespace':
                    namespace_node = child
                    break
            
            class_source_code = class_node.get('source_code', '')
            namespace_source_code = namespace_node.get('source_code', '') if namespace_node else ''
            
            # 获取依赖关系
            dependencies = target_file_info.get('dependencies', [])
            
            # 构建结果
            result = {
                'class_name': class_name,
                'cs_file': cs_file_path,
                'source_code': namespace_source_code if namespace_source_code else class_source_code,
                'class_source_code': class_source_code,  # 仅类的源代码（不含命名空间）
                'dependencies': dependencies,
                'dependency_count': len(dependencies)
            }
            
            # 缓存结果
            self.cs_source_cache[project_name][class_name] = result
            
            return result
            
        except Exception as e:
            self.logger.error(f"加载 CS 源代码失败 ({cs_json_file}): {str(e)}")
            return None
    
    def _load_dependency_classes_recursive(self, project_name: str, dependency_names: List[str], 
                                           visited: Optional[set] = None) -> List[Dict[str, Any]]:
        """
        递归加载所有依赖类的源代码（包括间接依赖）
        
        Args:
            project_name: 项目名称
            dependency_names: 依赖类名列表
            visited: 已访问的类名集合（用于避免循环依赖）
            
        Returns:
            依赖类的详细信息列表
        """
        if visited is None:
            visited = set()
        
        dependency_classes = []
        
        for dep_class_name in dependency_names:
            # 避免循环依赖和重复加载
            if dep_class_name in visited:
                continue
            
            visited.add(dep_class_name)
            
            dep_cs_info = self._load_cs_source_code(project_name, dep_class_name)
            if dep_cs_info:
                dep_info = {
                    'class_name': dep_class_name,
                    'cs_file': dep_cs_info.get('cs_file'),
                    'source_code': dep_cs_info.get('source_code'),
                    'class_source_code': dep_cs_info.get('class_source_code'),
                    'dependencies': dep_cs_info.get('dependencies', []),
                    'dependency_count': dep_cs_info.get('dependency_count', 0)
                }
                
                # 递归加载该类的依赖类
                if dep_cs_info.get('dependencies'):
                    nested_deps = self._load_dependency_classes_recursive(
                        project_name, dep_cs_info.get('dependencies', []), visited
                    )
                    if nested_deps:
                        dep_info['dependency_classes'] = nested_deps
                
                dependency_classes.append(dep_info)
        
        return dependency_classes
    
    def _extract_key(self, attributes: Dict[str, str]) -> Optional[str]:
        """
        从属性中提取 key（x:Key 或 Key）
        
        Args:
            attributes: 属性字典
            
        Returns:
            key 值，如果没有则返回 None
        """
        # 尝试 x:Key
        if 'Key' in attributes:
            return attributes['Key']
        
        # 尝试其他可能的 key 属性名
        for key_attr in ['x:Key', 'x:Name', 'Name']:
            if key_attr in attributes:
                return attributes[key_attr]
        
        return None
    
    def _extract_resource_info(self, node: Dict[str, Any], source_file: str, 
                               resource_index: int) -> Dict[str, Any]:
        """
        提取间接资源引用/依赖信息
        
        Args:
            node: JSON 节点
            source_file: 源文件路径
            resource_index: 资源索引
            
        Returns:
            间接资源引用/依赖信息字典
        """
        tag = node.get('tag', '')
        attributes = node.get('attributes', {})
        source_code = node.get('source_code', '')
        
        # 提取 key
        key = self._extract_key(attributes)
        
        # 构建间接资源引用/依赖信息（去除 full_tag 和 namespace 字段）
        resource_info = {
            'index': resource_index,
            'tag': tag,
            'source_file': source_file,
            'source_code': source_code,
            'attributes': attributes,
        }
        
        # 如果有 key，存储在 key 字段；否则存储在 info 字段
        if key:
            resource_info['key'] = key
            resource_info['info'] = None
        else:
            resource_info['key'] = None
            # 无 key 时，存储相关信息（标签名等）
            resource_info['info'] = {
                'tag': tag,
                'has_children': len(node.get('children', [])) > 0,
                'child_count': len(node.get('children', []))
            }
        
        # 如果是 Template 标签，标记为 template
        if self._is_template_tag(tag):
            resource_info['is_template'] = True
            resource_info['template_type'] = tag
        else:
            resource_info['is_template'] = False
            resource_info['template_type'] = None
        
        # 如果是数据资源，标记为 data_resource
        if self._is_data_resource(tag):
            resource_info['is_data_resource'] = True
            if self._is_data_provider_tag(tag):
                resource_info['data_resource_type'] = 'data_provider'
            else:
                resource_info['data_resource_type'] = 'custom_object'
        else:
            resource_info['is_data_resource'] = False
            resource_info['data_resource_type'] = None
        
        return resource_info
    
    def _extract_resources_from_node(self, node: Dict[str, Any], 
                                     source_file: str,
                                     resources: List[Dict[str, Any]],
                                     resource_index_counter: List[int],
                                     in_resources: bool = False,
                                     in_resource_dictionary: bool = False,
                                     is_direct_child: bool = False) -> None:
        """
        从 JSON 节点中递归提取间接资源引用/依赖信息
        
        Args:
            node: JSON 节点
            source_file: 源文件路径
            resources: 间接资源引用/依赖列表（用于收集结果）
            resource_index_counter: 资源索引计数器（使用列表以便在递归中共享）
            in_resources: 是否在 Resources 节点内
            in_resource_dictionary: 是否在 ResourceDictionary 节点内
            is_direct_child: 是否是 Resources/ResourceDictionary 的直接子节点
        """
        if not isinstance(node, dict):
            return
        
        tag = node.get('tag', '')
        children = node.get('children', [])
        
        # 检查是否是 Resources 节点
        if self._is_resources_node(tag):
            in_resources = True
            is_direct_child = False  # Resources 节点本身不是间接资源引用/依赖
            self.logger.debug(f"Found Resources node: {tag} in {source_file}")
        
        # 检查是否是 ResourceDictionary 节点
        elif self._is_resource_dictionary(tag):
            in_resource_dictionary = True
            is_direct_child = False  # ResourceDictionary 节点本身不是间接资源引用/依赖
            self.logger.debug(f"Found ResourceDictionary node in {source_file}")
        
        # 如果在 Resources 或 ResourceDictionary 内，且是直接子节点，提取间接资源引用/依赖
        elif (in_resources or in_resource_dictionary) and is_direct_child:
            # 跳过 ResourceDictionary.MergedDictionaries 等特殊子节点
            if not tag.startswith('ResourceDictionary.'):
                # 提取间接资源引用/依赖信息
                resource_index_counter[0] += 1
                resource_info = self._extract_resource_info(
                    node, source_file, resource_index_counter[0]
                )
                resources.append(resource_info)
                
                self.logger.debug(
                    f"Extracted resource #{resource_index_counter[0]}: "
                    f"{tag} (key: {resource_info.get('key', 'None')})"
                )
        
        # 递归处理子节点
        for child in children:
            # 判断是否是直接子节点：当前节点是 Resources 或 ResourceDictionary
            child_is_direct = (self._is_resources_node(tag) or 
                              self._is_resource_dictionary(tag))
            
            # 保持状态传递
            self._extract_resources_from_node(
                child, source_file, resources, resource_index_counter,
                in_resources, in_resource_dictionary, child_is_direct
            )
    
    def analyze_xaml_file(self, xaml_json_path: str) -> List[Dict[str, Any]]:
        """
        分析单个 XAML JSON 文件，提取间接资源引用/依赖
        
        Args:
            xaml_json_path: XAML JSON 文件路径
            
        Returns:
            间接资源引用/依赖列表
        """
        # 读取 XAML JSON 文件
        with open(xaml_json_path, 'r', encoding='utf-8') as f:
            xaml_data = json.load(f)
        
        # 获取源文件路径
        source_file = xaml_data.get('source_file', xaml_json_path)
        
        # 提取资源
        resources = []
        resource_index_counter = [0]  # 使用列表以便在递归中共享
        
        root = xaml_data.get('root', {})
        self._extract_resources_from_node(
            root, source_file, resources, resource_index_counter
        )
        
        self.logger.info(
            f"Extracted {len(resources)} resources from {Path(xaml_json_path).name}"
        )
        
        return resources
    
    def analyze_project(self, project_name: str) -> Dict[str, Any]:
        """
        分析项目的间接资源引用/依赖
        
        Args:
            project_name: 项目名称
            
        Returns:
            间接资源引用/依赖信息字典
        """
        # 查找 xaml 目录
        xaml_dir = self.output_base_dir / project_name / "xaml"
        
        if not xaml_dir.exists():
            raise FileNotFoundError(
                f"未找到项目 {project_name} 的 xaml 目录: {xaml_dir}"
            )
        
        # 查找所有 JSON 文件
        json_files = list(xaml_dir.glob("*.json"))
        
        if not json_files:
            self.logger.warning(f"在 {xaml_dir} 中未找到 JSON 文件")
            return {
                'project_name': project_name,
                'total_resources': 0,
                'resources': [],
                'summary': {
                    'by_file': {},
                    'by_template_type': {},
                    'with_key_count': 0,
                    'without_key_count': 0
                }
            }
        
        self.logger.info(f"开始分析项目: {project_name}")
        self.logger.info(f"找到 {len(json_files)} 个 JSON 文件")
        
        # 加载自定义类名（用于识别自定义数据对象）
        self._load_custom_class_names(project_name)
        
        # 分析所有文件
        all_resources = []
        data_resources_list = []  # 单独收集数据资源
        template_resources_list = []  # 单独收集模板资源
        resources_by_file = {}
        
        for json_file in json_files:
            try:
                resources = self.analyze_xaml_file(str(json_file))
                if resources:
                    file_name = json_file.name
                    resources_by_file[file_name] = len(resources)
                    all_resources.extend(resources)
                    
                    # 分离数据资源和模板资源
                    for resource in resources:
                        if resource.get('is_data_resource', False):
                            data_resources_list.append(resource)
                        if resource.get('is_template', False):
                            template_resources_list.append(resource)
            except Exception as e:
                self.logger.error(f"分析文件 {json_file.name} 时出错: {str(e)}")
        
        # 统计信息
        template_resources = [r for r in all_resources if r.get('is_template', False)]
        resources_with_key = [r for r in all_resources if r.get('key') is not None]
        resources_without_key = [r for r in all_resources if r.get('key') is None]
        
        # 按 Template 类型分组
        by_template_type = {}
        for resource in template_resources:
            template_type = resource.get('template_type')
            if template_type:
                if template_type not in by_template_type:
                    by_template_type[template_type] = []
                by_template_type[template_type].append(resource)
        
        # 构建按 key 索引的字典（便于快速查找）
        resources_by_key = {}
        for resource in resources_with_key:
            key = resource.get('key')
            if key:
                # 如果同一个 key 出现多次，存储为列表
                if key not in resources_by_key:
                    resources_by_key[key] = []
                resources_by_key[key].append(resource)
        
        # 构建结果
        result = {
            'project_name': project_name,
            'total_resources': len(all_resources),
            'resources': all_resources,  # 列表格式，便于遍历
            'resources_by_key': resources_by_key,  # 字典格式，便于通过 key 快速查找
            'summary': {
                'by_file': resources_by_file,
                'by_template_type': {k: len(v) for k, v in by_template_type.items()},
                'template_count': len(template_resources),
                'with_key_count': len(resources_with_key),
                'without_key_count': len(resources_without_key)
            }
        }
        
        self.resources[project_name] = result
        
        # 单独存储数据资源
        self.data_resources[project_name] = data_resources_list
        
        # 单独存储模板资源
        self.template_resources[project_name] = template_resources_list
        
        self.logger.info(f"找到 {len(data_resources_list)} 个数据资源")
        self.logger.info(f"找到 {len(template_resources_list)} 个模板资源")
        
        return result
    
    def save_to_json(self, project_name: str, output_dir: Optional[str] = None) -> str:
        """
        将间接资源引用/依赖信息保存为 JSON 文件
        注意：已保存到 data_resources.json 或 template_resources.json 的资源不会重复保存
        
        Args:
            project_name: 项目名称
            output_dir: 输出目录（如果为 None，则使用 outputs/{project_name}/dependency）
            
        Returns:
            输出文件的完整路径
        """
        if project_name not in self.resources:
            raise ValueError(
                f"项目 {project_name} 的间接资源引用/依赖信息不存在，请先调用 analyze_project"
            )
        
        # 确定输出目录：outputs/{project_name}/dependency/
        if output_dir is None:
            output_dir = self.output_base_dir / project_name / "dependency"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径
        output_file = output_dir / "indirect_resources.json"
        
        # 获取原始资源列表
        original_result = self.resources[project_name]
        all_resources = original_result.get('resources', [])
        
        # 构建数据资源和模板资源的唯一标识集合（用于排除）
        # 使用 source_file + key + tag 作为唯一标识（因为不同文件的资源可能有相同的 index）
        def get_resource_identifier(resource: Dict[str, Any]) -> str:
            """获取资源的唯一标识"""
            source_file = resource.get('source_file', '')
            key = resource.get('key', '')
            tag = resource.get('tag', '')
            # 如果没有 key，使用 source_code 的前100个字符作为标识
            if not key:
                source_code = resource.get('source_code', '')[:100]
                return f"{source_file}::{tag}::{source_code}"
            return f"{source_file}::{key}::{tag}"
        
        excluded_identifiers = set()
        
        if project_name in self.data_resources:
            for resource in self.data_resources[project_name]:
                excluded_identifiers.add(get_resource_identifier(resource))
        
        if project_name in self.template_resources:
            for resource in self.template_resources[project_name]:
                excluded_identifiers.add(get_resource_identifier(resource))
        
        # 过滤掉已保存到 data_resources.json 或 template_resources.json 的资源
        filtered_resources = [
            resource for resource in all_resources
            if get_resource_identifier(resource) not in excluded_identifiers
        ]
        
        # 重新统计信息
        resources_with_key = [r for r in filtered_resources if r.get('key') is not None]
        resources_without_key = [r for r in filtered_resources if r.get('key') is None]
        
        # 按文件统计
        resources_by_file = {}
        for resource in filtered_resources:
            source_file = resource.get('source_file', '')
            if source_file:
                # 从 source_file 中提取文件名
                file_name = Path(source_file).name + '.json'
                if file_name not in resources_by_file:
                    resources_by_file[file_name] = 0
                resources_by_file[file_name] += 1
        
        # 构建按 key 索引的字典（便于快速查找）
        resources_by_key = {}
        for resource in resources_with_key:
            key = resource.get('key')
            if key:
                if key not in resources_by_key:
                    resources_by_key[key] = []
                resources_by_key[key].append(resource)
        
        # 构建过滤后的结果
        filtered_result = {
            'project_name': project_name,
            'total_resources': len(filtered_resources),
            'resources': filtered_resources,  # 列表格式，便于遍历
            'resources_by_key': resources_by_key,  # 字典格式，便于通过 key 快速查找
            'summary': {
                'by_file': resources_by_file,
                'by_template_type': {},  # 模板资源已单独保存，这里不再统计
                'template_count': 0,  # 模板资源已单独保存
                'with_key_count': len(resources_with_key),
                'without_key_count': len(resources_without_key),
                'excluded_data_resources_count': len([r for r in all_resources if r.get('is_data_resource', False)]),
                'excluded_template_resources_count': len([r for r in all_resources if r.get('is_template', False)])
            }
        }
        
        # 保存为 JSON
        write_json(output_file, filtered_result)
        
        excluded_data_count = len([r for r in all_resources if r.get('is_data_resource', False)])
        excluded_template_count = len([r for r in all_resources if r.get('is_template', False)])
        
        self.logger.info(f"保存间接资源引用/依赖信息到: {output_file}")
        self.logger.info(f"已排除 {excluded_data_count} 个数据资源和 {excluded_template_count} 个模板资源")
        return str(output_file)
    
    def save_data_resources_to_json(self, project_name: str, output_dir: Optional[str] = None) -> str:
        """
        将数据资源信息单独保存为 JSON 文件
        
        Args:
            project_name: 项目名称
            output_dir: 输出目录（如果为 None，则使用 outputs/{project_name}/dependency）
            
        Returns:
            输出文件的完整路径
        """
        if project_name not in self.data_resources:
            raise ValueError(
                f"项目 {project_name} 的数据资源信息不存在，请先调用 analyze_project"
            )
        
        # 确定输出目录：outputs/{project_name}/dependency/
        if output_dir is None:
            output_dir = self.output_base_dir / project_name / "dependency"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径
        output_file = output_dir / "data_resources.json"
        
        # 统计信息
        data_resources_list = self.data_resources[project_name]
        data_providers = [r for r in data_resources_list if r.get('data_resource_type') == 'data_provider']
        custom_objects = [r for r in data_resources_list if r.get('data_resource_type') == 'custom_object']
        
        # 为自定义对象添加 CS 源代码和依赖信息
        enriched_data_resources = []
        for resource in data_resources_list:
            enriched_resource = resource.copy()
            
            # 如果是自定义对象，添加 CS 源代码和依赖信息
            if resource.get('data_resource_type') == 'custom_object':
                class_name = resource.get('tag', '')
                if class_name:
                    cs_info = self._load_cs_source_code(project_name, class_name)
                    if cs_info:
                        enriched_resource['class_info'] = {
                            'cs_file': cs_info.get('cs_file'),
                            'source_code': cs_info.get('source_code'),  # 包含命名空间的完整源代码
                            'class_source_code': cs_info.get('class_source_code'),  # 仅类的源代码
                            'dependencies': cs_info.get('dependencies', []),
                            'dependency_count': cs_info.get('dependency_count', 0)
                        }
                        
                        # 递归加载所有依赖类的源代码（包括间接依赖）
                        if cs_info.get('dependencies'):
                            dependency_classes = self._load_dependency_classes_recursive(
                                project_name, cs_info.get('dependencies', []), visited=set()
                            )
                            
                            if dependency_classes:
                                enriched_resource['class_info']['dependency_classes'] = dependency_classes
            
            enriched_data_resources.append(enriched_resource)
        
        # 构建结果
        result = {
            'project_name': project_name,
            'total_data_resources': len(data_resources_list),
            'data_resources': enriched_data_resources,
            'summary': {
                'data_provider_count': len(data_providers),
                'custom_object_count': len(custom_objects),
                'by_type': {
                    'XmlDataProvider': len([r for r in data_resources_list if r.get('tag') == 'XmlDataProvider']),
                    'ObjectDataProvider': len([r for r in data_resources_list if r.get('tag') == 'ObjectDataProvider']),
                    'CollectionViewSource': len([r for r in data_resources_list if r.get('tag') == 'CollectionViewSource']),
                    'custom_objects': len(custom_objects)
                }
            }
        }
        
        # 保存为 JSON
        write_json(output_file, result)
        
        self.logger.info(f"保存数据资源信息到: {output_file}")
        return str(output_file)
    
    def save_template_resources_to_json(self, project_name: str, output_dir: Optional[str] = None) -> str:
        """
        将模板资源信息单独保存为 JSON 文件
        
        Args:
            project_name: 项目名称
            output_dir: 输出目录（如果为 None，则使用 outputs/{project_name}/dependency）
            
        Returns:
            输出文件的完整路径
        """
        if project_name not in self.template_resources:
            raise ValueError(
                f"项目 {project_name} 的模板资源信息不存在，请先调用 analyze_project"
            )
        
        # 确定输出目录：outputs/{project_name}/dependency/
        if output_dir is None:
            output_dir = self.output_base_dir / project_name / "dependency"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径
        output_file = output_dir / "template_resources.json"
        
        # 统计信息
        template_resources_list = self.template_resources[project_name]
        
        # 加载 indirect_resources.json 以查找引用模板的资源
        indirect_resources = []
        indirect_resource_file = output_dir / "indirect_resources.json"
        if indirect_resource_file.exists():
            try:
                with open(indirect_resource_file, 'r', encoding='utf-8') as f:
                    indirect_data = json.load(f)
                    indirect_resources = indirect_data.get('resources', [])
                self.logger.info(f"加载了 {len(indirect_resources)} 个间接资源用于查找模板引用")
            except Exception as e:
                self.logger.warning(f"加载间接资源文件失败: {str(e)}")
        
        # 为每个模板查找所有引用它的资源
        enriched_template_resources = []
        
        for template_resource in template_resources_list:
            enriched_template = template_resource.copy()
            template_key = template_resource.get('key')
            
            if template_key:
                # 查找所有引用该模板的资源
                referenced_by = []
                
                # 匹配模式：{StaticResource TemplateKey} 或 {DynamicResource TemplateKey}
                # 注意：在 f-string 中，需要使用双大括号来转义大括号
                escaped_key = re.escape(template_key)
                static_pattern = r'\{StaticResource\s+' + escaped_key + r'\}'
                dynamic_pattern = r'\{DynamicResource\s+' + escaped_key + r'\}'
                
                for resource in indirect_resources:
                    source_code = resource.get('source_code', '')
                    resource_key = resource.get('key')
                    
                    # 检查是否引用了该模板
                    has_static_ref = bool(re.search(static_pattern, source_code))
                    has_dynamic_ref = bool(re.search(dynamic_pattern, source_code))
                    
                    if has_static_ref or has_dynamic_ref:
                        reference_type = 'StaticResource' if has_static_ref else 'DynamicResource'
                        
                        if resource_key:
                            referenced_by.append({
                                'key': resource_key,
                                'tag': resource.get('tag'),
                                'source_file': resource.get('source_file'),
                                'reference_type': reference_type
                            })
                        else:
                            # 如果没有 key，使用其他标识
                            referenced_by.append({
                                'key': None,
                                'tag': resource.get('tag'),
                                'source_file': resource.get('source_file'),
                                'info': resource.get('info'),
                                'reference_type': reference_type
                            })
                
                enriched_template['referenced_by'] = referenced_by
                enriched_template['referenced_by_count'] = len(referenced_by)
            else:
                enriched_template['referenced_by'] = []
                enriched_template['referenced_by_count'] = 0
            
            enriched_template_resources.append(enriched_template)
        
        # 按模板类型分组
        by_template_type = {}
        for resource in enriched_template_resources:
            template_type = resource.get('template_type')
            if template_type:
                if template_type not in by_template_type:
                    by_template_type[template_type] = []
                by_template_type[template_type].append(resource)
        
        # 构建按 key 索引的字典（便于快速查找）
        # 包括模板自身的 key 和所有引用该模板的资源的 key（间接引用）
        templates_by_key = {}
        for resource in enriched_template_resources:
            key = resource.get('key')
            if key:
                # 如果同一个 key 出现多次，存储为列表
                if key not in templates_by_key:
                    templates_by_key[key] = []
                templates_by_key[key].append(resource)
            
            # 添加间接引用：如果该模板被其他资源引用，且引用者有 key，则可以通过引用者的 key 找到该模板
            referenced_by = resource.get('referenced_by', [])
            if referenced_by:
                for ref_info in referenced_by:
                    ref_key = ref_info.get('key')
                    if ref_key:
                        # 通过引用者的 key 也可以找到该模板
                        if ref_key not in templates_by_key:
                            templates_by_key[ref_key] = []
                        # 避免重复添加（如果引用者的 key 恰好也是模板的 key）
                        if resource not in templates_by_key[ref_key]:
                            templates_by_key[ref_key].append(resource)
        
        # 构建结果
        result = {
            'project_name': project_name,
            'total_template_resources': len(enriched_template_resources),
            'template_resources': enriched_template_resources,
            'templates_by_key': templates_by_key,  # 字典格式，便于通过 key 快速查找
            'summary': {
                'by_template_type': {k: len(v) for k, v in by_template_type.items()},
                'with_key_count': len([r for r in enriched_template_resources if r.get('key')]),
                'without_key_count': len([r for r in enriched_template_resources if not r.get('key')]),
                'total_referenced_by_count': sum(r.get('referenced_by_count', 0) for r in enriched_template_resources)
            }
        }
        
        # 保存为 JSON
        write_json(output_file, result)
        
        self.logger.info(f"保存模板资源信息到: {output_file}")
        return str(output_file)
    
    @staticmethod
    def analyze_project_static(project_name: str, output_base_dir: str = "outputs") -> tuple:
        """
        分析项目间接资源引用/依赖并保存（静态方法，便于调用）
        
        Args:
            project_name: 项目名称
            output_base_dir: 输出基础目录（默认为 "outputs"）
            
        Returns:
            (间接资源引用/依赖信息字典, 输出文件路径, 数据资源文件路径, 模板资源文件路径)
        """
        analyzer = LayoutResourceDependencyAnalyzer(output_base_dir)
        
        # 分析资源
        result = analyzer.analyze_project(project_name)
        
        # 保存结果
        output_file = analyzer.save_to_json(project_name)
        
        # 保存数据资源
        data_resources_file = analyzer.save_data_resources_to_json(project_name)
        
        # 保存模板资源
        template_resources_file = analyzer.save_template_resources_to_json(project_name)
        
        return result, output_file, data_resources_file, template_resources_file
    
    def print_summary(self, project_name: str):
        """打印间接资源引用/依赖摘要"""
        if project_name not in self.resources:
            self.logger.warning(f"项目 {project_name} 的间接资源引用/依赖信息不存在")
            return
        
        result = self.resources[project_name]
        
        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"项目: {result['project_name']}")
        self.logger.info("=" * 70)
        self.logger.info(f"总资源数: {result['total_resources']}")
        self.logger.info("")
        
        if result['total_resources'] == 0:
            self.logger.info("未找到任何间接资源引用/依赖")
            return
        
        summary = result['summary']
        
        # 按文件显示
        self.logger.info("按文件统计:")
        for file_name, count in summary['by_file'].items():
            self.logger.info(f"  {file_name}: {count} 个资源")
        
        self.logger.info("")
        
        # Template 统计
        self.logger.info(f"Template 资源: {summary['template_count']} 个")
        if summary['by_template_type']:
            self.logger.info("Template 类型统计:")
            for template_type, count in summary['by_template_type'].items():
                self.logger.info(f"  {template_type}: {count} 个")
        
        self.logger.info("")
        
        # Key 统计
        self.logger.info(f"有 Key 的资源: {summary['with_key_count']} 个")
        self.logger.info(f"无 Key 的资源: {summary['without_key_count']} 个")
        
        self.logger.info("\n" + "=" * 70)


# python -m src.parser.indirect_resource_analysis
if __name__ == "__main__":
    # from src.parser.indirect_resource_analysis import LayoutResourceDependencyAnalyzer

    # 方式1：使用静态方法（推荐）
    result, output_file, data_resources_file, template_resources_file = LayoutResourceDependencyAnalyzer.analyze_project_static(
        "ExpenseItDemo",
        "outputs"
    )

    # 方式2：使用实例方法
    # analyzer = LayoutResourceDependencyAnalyzer("outputs")
    # result = analyzer.analyze_project("ExpenseItDemo")
    # output_file = analyzer.save_to_json("ExpenseItDemo")
    # data_resources_file = analyzer.save_data_resources_to_json("ExpenseItDemo")
    # template_resources_file = analyzer.save_template_resources_to_json("ExpenseItDemo")
    # analyzer.print_summary("ExpenseItDemo")
