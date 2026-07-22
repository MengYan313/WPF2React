"""
静态资源依赖关系识别模块
用于识别和定位 WPF 项目中的静态资源（如图片、字体、数据文件等）
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple

from src.common.logging import get_logger
from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    artifact_source_id,
    mirrored_json_path,
    require_identity_scheme,
    repository_relative_id,
)
from src.parser.io_utils import write_json


class ResourceDependencyAnalyzer:
    """静态资源依赖关系分析器"""
    
    # 常见的资源标签类型
    RESOURCE_TAGS = {
        'Resource',           # 嵌入资源
        'Content',            # 内容文件
        'EmbeddedResource',   # 嵌入式资源
        'None',               # 无操作（但可能是资源）
        'ApplicationDefinition',  # 应用程序定义
        'Page',               # XAML 页面
        'Compile'             # 编译文件（某些情况下包含资源）
    }
    
    # 常见的资源文件扩展名
    RESOURCE_EXTENSIONS = {
        # 图片
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.tif', '.tiff',
        # 字体
        '.ttf', '.otf', '.woff', '.woff2',
        # 音频视频
        '.mp3', '.wav', '.mp4', '.avi', '.wmv',
        # 数据文件
        '.xml', '.json', '.txt', '.csv',
        # 其他
        '.cur',  # 光标文件
        '.resx', # 资源文件
    }
    
    def __init__(self, output_base_dir: str = "outputs"):
        """
        初始化分析器
        
        Args:
            output_base_dir: 输出基础目录（默认为 "outputs"）
        """
        self.output_base_dir = Path(output_base_dir)
        self.resources: Dict[str, List[Dict[str, Any]]] = {}  # {项目名: [资源列表]}
        self._reference_contexts: Dict[str, Dict[str, Any]] = {}
        self._resource_pattern_cache: Dict[Tuple[str, ...], re.Pattern[str]] = {}
        
        # 初始化日志
        self.logger = get_logger("resource_dependency")
    
    def _extract_resource_name_variants(self, resource: Dict[str, Any]) -> Set[str]:
        """
        提取资源文件名的所有可能变体（用于匹配引用）
        
        Args:
            resource: 资源信息字典
            
        Returns:
            资源文件名的所有可能变体集合
        """
        file_name = resource.get('file_name', '')
        file_path = resource.get('file_path', '')
        
        variants = set()
        
        # 完整文件名（带扩展名）
        variants.add(file_name)
        variants.add(file_name.lower())
        variants.add(file_name.upper())
        
        # 文件名（不含扩展名）
        name_without_ext = os.path.splitext(file_name)[0]
        variants.add(name_without_ext)
        variants.add(name_without_ext.lower())
        variants.add(name_without_ext.upper())
        
        # 路径中的文件名
        if file_path and file_path != file_name:
            path_name = os.path.basename(file_path)
            variants.add(path_name)
            variants.add(path_name.lower())
            variants.add(os.path.splitext(path_name)[0])
            variants.add(os.path.splitext(path_name)[0].lower())
        
        # 处理 WPF 资源路径格式：/AssemblyName;component/path/to/file.ext
        # 提取最后的文件名部分
        if ';component/' in file_path:
            component_part = file_path.split(';component/')[-1]
            variants.add(component_part)
            variants.add(os.path.basename(component_part))
            variants.add(os.path.splitext(os.path.basename(component_part))[0])
        
        return variants
    
    def _find_resource_in_text(self, text: str, resource_variants: Set[str]) -> bool:
        """
        在文本中查找资源引用
        
        Args:
            text: 要搜索的文本
            resource_variants: 资源文件名的所有可能变体
            
        Returns:
            是否找到引用
        """
        key = tuple(sorted({variant.lower() for variant in resource_variants if variant}))
        if not text or not key:
            return False
        pattern = self._resource_pattern_cache.get(key)
        if pattern is None:
            alternatives = "|".join(
                re.escape(variant) for variant in sorted(key, key=lambda value: (-len(value), value))
            )
            pattern = re.compile(
                rf'(?:["\'][^"\']*(?:{alternatives})["\']|'
                rf'[/;][^/;]*(?:{alternatives})|'
                rf'component/[^"\']*(?:{alternatives}))',
                re.IGNORECASE,
            )
            self._resource_pattern_cache[key] = pattern
        return pattern.search(text) is not None

    def _load_reference_context(self, project_name: str) -> Dict[str, Any]:
        """一次加载页面与间接资源，避免每个静态资源重复读盘。"""
        if project_name in self._reference_contexts:
            return self._reference_contexts[project_name]

        dependency_dir = self.output_base_dir / project_name / "dependency"
        page_dependency_file = dependency_dir / "page_dependency.json"
        context: Dict[str, Any] = {"pages": {}, "page_json": {}, "indirect": []}
        if not page_dependency_file.exists():
            self.logger.warning(f"未找到页面依赖文件: {page_dependency_file}")
            self._reference_contexts[project_name] = context
            return context

        with open(page_dependency_file, 'r', encoding='utf-8') as f:
            page_dependency = json.load(f)
        require_identity_scheme(page_dependency, page_dependency_file)
        context["pages"] = page_dependency.get('pages', {})

        for indirect_file in [
            dependency_dir / "indirect_resources.json",
            dependency_dir / "indirect_resource_dependency.json",
        ]:
            if indirect_file.exists():
                with open(indirect_file, 'r', encoding='utf-8') as f:
                    context["indirect"] = json.load(f).get('resources', [])
                break

        xaml_output_dir = self.output_base_dir / project_name / "xaml"
        for page_id, page_info in context["pages"].items():
            xaml_file = page_info.get('xaml_file', '')
            if not xaml_file:
                continue
            xaml_json_file = mirrored_json_path(xaml_output_dir, page_id)
            if xaml_json_file.exists() and page_id not in context["page_json"]:
                with open(xaml_json_file, 'r', encoding='utf-8') as f:
                    xaml_data = json.load(f)
                artifact_source_id(xaml_data, xaml_json_file)
                context["page_json"][page_id] = xaml_data

        self._reference_contexts[project_name] = context
        return context

    def _precompute_indirect_resource_keys(
        self, project_name: str, resources: List[Dict[str, Any]]
    ) -> None:
        """一次扫描间接资源，将 Style/Template key 批量映射到文件。"""
        if not resources:
            return
        context = self._load_reference_context(project_name)
        indirect_resources = context["indirect"]
        variant_to_resources: Dict[str, Set[int]] = defaultdict(set)
        for index, resource in enumerate(resources):
            for variant in self._extract_resource_name_variants(resource):
                if variant:
                    variant_to_resources[variant.lower()].add(index)
            resource['_style_keys'] = set()
            resource['_template_keys'] = set()

        if not indirect_resources or not variant_to_resources:
            return
        alternatives = "|".join(
            re.escape(variant)
            for variant in sorted(
                variant_to_resources, key=lambda value: (-len(value), value)
            )
        )
        pattern = re.compile(alternatives, re.IGNORECASE)
        for indirect_resource in indirect_resources:
            source_code = indirect_resource.get('source_code', '')
            matched_indices = {
                index
                for match in pattern.finditer(source_code)
                for index in variant_to_resources[match.group(0).lower()]
            }
            if not matched_indices:
                continue
            resource_key = indirect_resource.get('key')
            if not resource_key:
                continue
            key_type = (
                '_template_keys'
                if indirect_resource.get('is_template', False)
                else '_style_keys'
                if indirect_resource.get('tag', '') == 'Style'
                else None
            )
            if key_type:
                for index in matched_indices:
                    resources[index][key_type].add(resource_key)
    
    def _find_pages_using_resource(self, project_name: str, resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        查找使用该资源的所有页面
        
        Args:
            project_name: 项目名称
            resource: 资源信息字典
            
        Returns:
            引用该资源的页面列表，每个元素包含页面信息和引用类型
        """
        referenced_by_pages = []
        
        # 获取资源文件名的所有变体
        resource_variants = self._extract_resource_name_variants(resource)
        has_precomputed_keys = (
            '_style_keys' in resource or '_template_keys' in resource
        )
        style_keys_using_resource = set(resource.pop('_style_keys', set()))
        template_keys_using_resource = set(resource.pop('_template_keys', set()))

        context = self._load_reference_context(project_name)
        pages = context["pages"]
        if not pages:
            return referenced_by_pages
        
        try:
            if not has_precomputed_keys:
                for indirect_resource in context["indirect"]:
                    source_code = indirect_resource.get('source_code', '')
                    if self._find_resource_in_text(source_code, resource_variants):
                        resource_key = indirect_resource.get('key')
                        resource_tag = indirect_resource.get('tag', '')
                        if resource_key:
                            if indirect_resource.get('is_template', False):
                                template_keys_using_resource.add(resource_key)
                            elif resource_tag == 'Style':
                                style_keys_using_resource.add(resource_key)
            
            # 检查每个页面
            for page_name in sorted(pages):
                page_info = pages[page_name]
                xaml_file = page_info.get('xaml_file', '')
                if not xaml_file:
                    continue
                
                xaml_data = context["page_json"].get(page_name)
                if not xaml_data:
                    continue
                
                try:
                    root = xaml_data.get('root', {})
                    source_code = root.get('source_code', '')
                    attributes = root.get('attributes', {})
                    
                    # 递归检查所有节点的属性值，提取源代码片段
                    def extract_source_snippets(node: Dict[str, Any], resource_variants: Set[str], 
                                               depth: int = 0, max_depth: int = 20) -> List[str]:
                        """递归检查节点及其子节点中的资源引用，提取最小源代码片段"""
                        snippets = []
                        if depth > max_depth:
                            return snippets
                        
                        node_attrs = node.get('attributes', {})
                        node_tag = node.get('tag', '')
                        
                        # 检查当前节点的属性值，只提取包含资源引用的属性
                        for attr_name, attr_value in node_attrs.items():
                            if isinstance(attr_value, str) and self._find_resource_in_text(attr_value, resource_variants):
                                # 只提取包含资源引用的属性，格式：属性名="属性值"
                                snippets.append(f'{attr_name}="{attr_value}"')
                        
                        # 递归检查子节点
                        for child in node.get('children', []):
                            snippets.extend(extract_source_snippets(child, resource_variants, depth + 1, max_depth))
                        
                        return snippets
                    
                    # 检查直接引用并提取源代码片段
                    is_direct_reference = False
                    source_snippets = []
                    
                    # 检查根节点的属性值
                    for attr_name, attr_value in attributes.items():
                        if isinstance(attr_value, str) and self._find_resource_in_text(attr_value, resource_variants):
                            is_direct_reference = True
                            # 只提取属性名和属性值，格式：属性名="属性值"
                            source_snippets.append(f'{attr_name}="{attr_value}"')
                    
                    # 递归检查所有节点的源代码片段
                    node_snippets = extract_source_snippets(root, resource_variants)
                    if node_snippets:
                        is_direct_reference = True
                        source_snippets.extend(node_snippets)
                    
                    # 去重
                    if source_snippets:
                        unique_snippets = []
                        seen = set()
                        for snippet in source_snippets:
                            snippet_lower = snippet.lower()
                            if snippet_lower not in seen:
                                unique_snippets.append(snippet)
                                seen.add(snippet_lower)
                        source_snippets = unique_snippets
                    
                    # 检查通过 Style 的间接引用
                    is_indirect_via_style = False
                    style_references = []
                    
                    # 在源代码中查找 Style 引用
                    for style_key in sorted(style_keys_using_resource):
                        style_pattern = rf'Style\s*=\s*["\']{{StaticResource\s+{re.escape(style_key)}}}["\']'
                        if re.search(style_pattern, source_code, re.IGNORECASE):
                            is_indirect_via_style = True
                            style_references.append(style_key)
                    
                    # 检查通过 Template 的间接引用
                    is_indirect_via_template = False
                    template_references = []
                    
                    for template_key in sorted(template_keys_using_resource):
                        template_patterns = [
                            rf'Template\s*=\s*["\']{{StaticResource\s+{re.escape(template_key)}}}["\']',
                            rf'ItemTemplate\s*=\s*["\']{{StaticResource\s+{re.escape(template_key)}}}["\']',
                            rf'ContentTemplate\s*=\s*["\']{{StaticResource\s+{re.escape(template_key)}}}["\']',
                        ]
                        for pattern in template_patterns:
                            if re.search(pattern, source_code, re.IGNORECASE):
                                is_indirect_via_template = True
                                template_references.append(template_key)
                                break
                    
                    # 如果找到任何引用，添加到结果列表
                    if is_direct_reference or is_indirect_via_style or is_indirect_via_template:
                        page_ref_info = {
                            'page_id': page_name,
                            'xaml_file': xaml_file,
                            'source_code': None,  # 直接引用，如果没有则为 None
                            'style_references': [],  # 间接引用（通过 Style），如果没有则为空数组
                            'template_references': []  # 间接引用（通过 Template），如果没有则为空数组
                        }
                        
                        # 如果是直接引用，保留源代码片段
                        if is_direct_reference and source_snippets:
                            # 如果只有一个片段，直接存储字符串；否则存储数组
                            page_ref_info['source_code'] = source_snippets[0] if len(source_snippets) == 1 else source_snippets
                        
                        # 如果是间接引用，保留 Style 或 Template 引用
                        if is_indirect_via_style:
                            page_ref_info['style_references'] = style_references
                        
                        if is_indirect_via_template:
                            page_ref_info['template_references'] = template_references
                        
                        referenced_by_pages.append(page_ref_info)
                
                except Exception as e:
                    self.logger.warning(f"分析页面 {page_name} 时出错: {str(e)}")
                    continue
        
        except Exception as e:
            self.logger.error(f"加载页面依赖文件失败: {str(e)}")
        
        return referenced_by_pages
    
    def find_csproj_json_files(self, project_name: str) -> List[Path]:
        """查找项目的全部 .csproj.json 文件。"""
        xaml_output_dir = self.output_base_dir / project_name / "xaml"
        if not xaml_output_dir.exists():
            return []
        return sorted(xaml_output_dir.rglob("*.csproj.json"))

    def find_csproj_json(self, project_name: str) -> Optional[Path]:
        """
        查找项目的 .csproj.json 文件
        
        Args:
            project_name: 项目名称
            
        Returns:
            .csproj.json 文件路径，如果不存在返回 None
        """
        csproj_files = self.find_csproj_json_files(project_name)
        return csproj_files[0] if csproj_files else None
    
    def extract_resources_from_node(self, node: Dict[str, Any], 
                                    resources: List[Dict[str, Any]],
                                    parent_tag: Optional[str] = None) -> None:
        """
        从 JSON 节点中递归提取资源信息
        
        Args:
            node: JSON 节点
            resources: 资源列表（用于收集结果）
            parent_tag: 父节点的标签名
        """
        if not isinstance(node, dict):
            return
        
        tag = node.get('tag', '')
        attributes = node.get('attributes', {})
        
        # 检查是否是资源相关的标签
        if tag in self.RESOURCE_TAGS and 'Include' in attributes:
            include_path = attributes['Include']
            
            # 检查文件扩展名是否是资源类型
            ext = os.path.splitext(include_path)[1].lower()
            
            # 对于 Resource, Content, EmbeddedResource 标签，或者扩展名匹配的文件
            if tag in {'Resource', 'Content', 'EmbeddedResource'} or ext in self.RESOURCE_EXTENSIONS:
                resource_info = {
                    'resource_type': tag,
                    'file_path': include_path,
                    'file_name': os.path.basename(include_path),
                    'extension': ext,
                    'attributes': attributes
                }
                
                # 添加额外的属性信息
                if 'Link' in attributes:
                    resource_info['link'] = attributes['Link']
                
                if 'CopyToOutputDirectory' in attributes:
                    resource_info['copy_to_output'] = attributes['CopyToOutputDirectory']
                
                resources.append(resource_info)
        
        # 递归处理子节点
        children = node.get('children', [])
        for child in children:
            self.extract_resources_from_node(child, resources, tag)
    
    def analyze_project_resources(self, project_name: str, 
                                  project_path: Optional[str] = None) -> Dict[str, Any]:
        """
        分析项目的静态资源
        
        Args:
            project_name: 项目名称
            project_path: 项目实际路径（用于验证资源文件是否存在）
            
        Returns:
            资源依赖信息字典
        """
        csproj_json_paths = self.find_csproj_json_files(project_name)
        csproj_records = []
        resources = []

        for csproj_json_path in csproj_json_paths:
            with open(csproj_json_path, 'r', encoding='utf-8') as f:
                csproj_data = json.load(f)
            source_csproj = csproj_data.get('source_file', 'unknown')
            csproj_records.append((csproj_json_path, source_csproj))
            project_resources: List[Dict[str, Any]] = []
            self.extract_resources_from_node(
                csproj_data.get('root', {}), project_resources
            )
            for resource in project_resources:
                resource['source_csproj'] = source_csproj
                resources.append(resource)

        if not csproj_json_paths:
            self.logger.warning(
                f"未找到项目 {project_name} 的 .csproj.json 文件，"
                "将保留空资源结果"
            )

        # 同一项目文件内的重复 Include 不应重复计数。
        unique_resources = {}
        for resource in resources:
            key = (
                resource.get('source_csproj', ''),
                resource.get('resource_type', ''),
                resource.get('file_path', ''),
            )
            unique_resources[key] = resource
        resources = [unique_resources[key] for key in sorted(unique_resources)]
        
        # 如果提供了项目路径，验证资源文件是否存在
        if project_path:
            for resource in resources:
                file_path = resource['file_path']
                # 处理 Windows 路径分隔符
                file_path = file_path.replace('\\', '/')
                source_csproj = Path(resource.get('source_csproj', ''))
                if source_csproj.is_absolute():
                    csproj_parent = source_csproj.parent
                elif source_csproj.exists():
                    csproj_parent = source_csproj.parent
                else:
                    csproj_parent = Path(project_path) / source_csproj.parent
                full_path = csproj_parent / file_path
                resource['exists'] = full_path.exists()
                resource['absolute_path'] = str(full_path) if full_path.exists() else None
                try:
                    resource['source_id'] = repository_relative_id(
                        full_path, project_path
                    )
                except ValueError:
                    resource['source_id'] = None
        
        # 分析每个资源被哪些页面引用
        self.logger.info("分析资源页面引用关系...")
        self._precompute_indirect_resource_keys(project_name, resources)
        for resource in resources:
            referenced_by_pages = self._find_pages_using_resource(project_name, resource)
            resource['referenced_by_pages'] = referenced_by_pages
            resource['referenced_by_pages_count'] = len(referenced_by_pages)
            
            if referenced_by_pages:
                page_names = [p['page_id'] for p in referenced_by_pages]
                self.logger.debug(f"资源 {resource['file_name']} 被以下页面引用: {', '.join(page_names)}")
        
        # 按资源类型分组
        resources_by_type = {}
        for resource in resources:
            res_type = resource['resource_type']
            if res_type not in resources_by_type:
                resources_by_type[res_type] = []
            resources_by_type[res_type].append(resource)
        
        # 按扩展名分组
        resources_by_extension = {}
        for resource in resources:
            ext = resource['extension']
            if ext not in resources_by_extension:
                resources_by_extension[ext] = []
            resources_by_extension[ext].append(resource)
        
        # 统计页面引用信息
        total_referenced_by_pages = sum(1 for r in resources if r.get('referenced_by_pages_count', 0) > 0)
        total_unreferenced = sum(1 for r in resources if r.get('referenced_by_pages_count', 0) == 0)
        
        # 按引用类型统计
        direct_ref_count = sum(1 for r in resources 
                              for p in r.get('referenced_by_pages', [])
                              if 'source_code' in p)
        indirect_style_ref_count = sum(1 for r in resources 
                                       for p in r.get('referenced_by_pages', [])
                                       if 'style_references' in p)
        indirect_template_ref_count = sum(1 for r in resources 
                                         for p in r.get('referenced_by_pages', [])
                                         if 'template_references' in p)
        
        # 构建结果
        result = {
            'id_scheme': SOURCE_ID_SCHEME,
            'project_name': project_name,
            # 保留单数字段以兼容现有资源迁移消费端。
            'csproj_file': (
                str(csproj_records[0][0].relative_to(self.output_base_dir))
                if csproj_records else None
            ),
            'csproj_files': [
                str(path.relative_to(self.output_base_dir))
                for path, _ in csproj_records
            ],
            'source_csproj': csproj_records[0][1] if csproj_records else None,
            'source_csproj_files': [source for _, source in csproj_records],
            'project_file_missing': not csproj_records,
            'total_resources': len(resources),
            'resources': resources,
            'summary': {
                'by_type': {k: len(v) for k, v in resources_by_type.items()},
                'by_extension': {k: len(v) for k, v in resources_by_extension.items()},
                'exists_count': sum(1 for r in resources if r.get('exists', False)),
                'missing_count': sum(1 for r in resources if r.get('exists') is False),
                'referenced_by_pages_count': total_referenced_by_pages,
                'unreferenced_count': total_unreferenced,
                'reference_type_stats': {
                    'direct_references': direct_ref_count,
                    'indirect_via_style': indirect_style_ref_count,
                    'indirect_via_template': indirect_template_ref_count
                }
            }
        }
        
        self.resources[project_name] = result
        return result
    
    def save_to_json(self, project_name: str, output_dir: Optional[str] = None) -> str:
        """
        将资源依赖信息保存为 JSON 文件
        
        Args:
            project_name: 项目名称
            output_dir: 输出目录（如果为 None，则使用 outputs/{project_name}/dependency）
            
        Returns:
            输出文件的完整路径
        """
        if project_name not in self.resources:
            raise ValueError(f"项目 {project_name} 的资源信息不存在，请先调用 analyze_project_resources")
        
        # 确定输出目录：outputs/{project_name}/dependency/
        if output_dir is None:
            output_dir = self.output_base_dir / project_name / "dependency"
        else:
            output_dir = Path(output_dir)
        
        # 输出文件路径
        output_file = output_dir / "resource_dependency.json"
        write_json(output_file, self.resources[project_name])
        
        return str(output_file)
    
    @staticmethod
    def analyze_project(project_name: str, project_path: Optional[str] = None,
                       output_base_dir: str = "outputs") -> Tuple[Dict[str, Any], str]:
        """
        分析项目资源并保存（静态方法，便于调用）
        
        Args:
            project_name: 项目名称
            project_path: 项目实际路径（用于验证资源文件）
            output_base_dir: 输出基础目录
            
        Returns:
            (资源依赖信息字典, 输出文件路径)
        """
        analyzer = ResourceDependencyAnalyzer(output_base_dir)
        
        # 分析资源
        result = analyzer.analyze_project_resources(project_name, project_path)
        
        # 保存结果
        output_file = analyzer.save_to_json(project_name)
        
        return result, output_file
    
    def print_summary(self, project_name: str):
        """打印资源依赖摘要"""
        if project_name not in self.resources:
            self.logger.warning(f"项目 {project_name} 的资源信息不存在")
            return
        
        result = self.resources[project_name]
        
        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"项目: {result['project_name']}")
        self.logger.info("=" * 70)
        self.logger.info(f"源文件: {result['source_csproj']}")
        self.logger.info(f"总资源数: {result['total_resources']}")
        self.logger.info("")
        
        if result['total_resources'] == 0:
            self.logger.info("未找到任何资源文件")
            return
        
        # 按类型显示
        self.logger.info("资源类型统计:")
        for res_type, count in result['summary']['by_type'].items():
            self.logger.info(f"  {res_type}: {count} 个")
        
        self.logger.info("")
        
        # 按扩展名显示
        if result['summary']['by_extension']:
            self.logger.info("文件类型统计:")
            for ext, count in result['summary']['by_extension'].items():
                ext_display = ext if ext else '(无扩展名)'
                self.logger.info(f"  {ext_display}: {count} 个")
        
        self.logger.info("")
        
        # 显示资源列表
        self.logger.info("资源列表:")
        self.logger.debug("-" * 70)
        for i, resource in enumerate(result['resources'], 1):
            self.logger.info(f"\n{i}. {resource['file_name']}")
            self.logger.info(f"   类型: {resource['resource_type']}")
            self.logger.info(f"   路径: {resource['file_path']}")
            
            if 'exists' in resource:
                status = "✓ 存在" if resource['exists'] else "✗ 缺失"
                self.logger.info(f"   状态: {status}")
            
            if 'link' in resource:
                self.logger.info(f"   链接: {resource['link']}")
            
            if 'copy_to_output' in resource:
                self.logger.info(f"   复制到输出: {resource['copy_to_output']}")
        
        self.logger.info("\n" + "=" * 70)


# 运行示例：python -m src.parser.resource_dependency
if __name__ == "__main__":
    # 导入示例：from src.parser.resource_dependency import ResourceDependencyAnalyzer
    
    logger = get_logger("resource_dependency")
    
    logger.info("=" * 70)
    logger.info("资源依赖分析")
    logger.info("=" * 70)
    
    # 方式1：使用静态方法（推荐）
    result, output_file = ResourceDependencyAnalyzer.analyze_project(
        "ExpenseItDemo",
        "repos/ExpenseItDemo"
    )
    
    logger.info(f"\n✓ 项目: ExpenseItDemo")
    logger.info(f"✓ 找到 {len(result)} 个资源")
    logger.info(f"✓ 输出文件: {output_file}")
    
    # 打印详细摘要
    analyzer = ResourceDependencyAnalyzer()
    analyzer.resources["ExpenseItDemo"] = result
    analyzer.print_summary("ExpenseItDemo")

    # 方式2：使用实例方法
    # 示例：analyzer = ResourceDependencyAnalyzer()
    # 示例：result = analyzer.analyze_project_resources("ExpenseItDemo", "repos/ExpenseItDemo")
    # 示例：output_file = analyzer.save_to_json("ExpenseItDemo")
    # analyzer.print_summary("ExpenseItDemo")  # 打印详细摘要
