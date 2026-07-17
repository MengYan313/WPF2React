"""
静态资源依赖关系识别模块
用于识别和定位 WPF 项目中的静态资源（如图片、字体、数据文件等）
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple

from src.common.logging import get_logger
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
        text_lower = text.lower()
        
        for variant in resource_variants:
            variant_lower = variant.lower()
            # 检查是否在引号内（属性值）或路径中
            # 匹配模式：引号内的文件名、路径中的文件名、component/路径格式
            patterns = [
                rf'["\']([^"\']*{re.escape(variant_lower)})["\']',  # 引号内的引用
                rf'[/;]([^/;]*{re.escape(variant_lower)})',  # 路径中的引用
                rf'component/([^"\']*{re.escape(variant_lower)})',  # component/路径格式
            ]
            
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return True
        
        return False
    
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
        
        # 加载页面依赖信息
        page_dependency_file = self.output_base_dir / project_name / "dependency" / "page_dependency.json"
        if not page_dependency_file.exists():
            self.logger.warning(f"未找到页面依赖文件: {page_dependency_file}")
            return referenced_by_pages
        
        try:
            with open(page_dependency_file, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
            
            pages = page_data.get('pages', {})
            
            # 加载间接资源信息（用于查找 Style/Template 中的引用）
            indirect_resources = []
            indirect_file1 = self.output_base_dir / project_name / "dependency" / "indirect_resources.json"
            indirect_file2 = self.output_base_dir / project_name / "dependency" / "indirect_resource_dependency.json"
            
            if indirect_file1.exists():
                with open(indirect_file1, 'r', encoding='utf-8') as f:
                    indirect_data = json.load(f)
                    indirect_resources = indirect_data.get('resources', [])
            elif indirect_file2.exists():
                with open(indirect_file2, 'r', encoding='utf-8') as f:
                    indirect_data = json.load(f)
                    indirect_resources = indirect_data.get('resources', [])
            
            # 构建 Style/Template key 到资源的映射（哪些 Style/Template 引用了该资源）
            style_keys_using_resource = set()
            template_keys_using_resource = set()
            
            for indirect_resource in indirect_resources:
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
            for page_name, page_info in pages.items():
                xaml_file = page_info.get('xaml_file', '')
                if not xaml_file:
                    continue
                
                # 从 xaml_file 路径中提取文件名（不含扩展名）
                xaml_file_name = Path(xaml_file).stem
                
                # 读取页面 XAML JSON 文件
                xaml_json_file = self.output_base_dir / project_name / "xaml" / f"{xaml_file_name}.xaml.json"
                
                if not xaml_json_file.exists():
                    continue
                
                try:
                    with open(xaml_json_file, 'r', encoding='utf-8') as f:
                        xaml_data = json.load(f)
                    
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
                    for style_key in style_keys_using_resource:
                        style_pattern = rf'Style\s*=\s*["\']{{StaticResource\s+{re.escape(style_key)}}}["\']'
                        if re.search(style_pattern, source_code, re.IGNORECASE):
                            is_indirect_via_style = True
                            style_references.append(style_key)
                    
                    # 检查通过 Template 的间接引用
                    is_indirect_via_template = False
                    template_references = []
                    
                    for template_key in template_keys_using_resource:
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
                            'page_name': page_name,
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
    
    def find_csproj_json(self, project_name: str) -> Optional[Path]:
        """
        查找项目的 .csproj.json 文件
        
        Args:
            project_name: 项目名称
            
        Returns:
            .csproj.json 文件路径，如果不存在返回 None
        """
        # .csproj.json 文件现在存储在 xaml/ 子目录下
        xaml_output_dir = self.output_base_dir / project_name / "xaml"
        
        if not xaml_output_dir.exists():
            return None
        
        # 查找 .csproj.json 文件
        csproj_files = list(xaml_output_dir.glob("*.csproj.json"))
        
        if not csproj_files:
            return None
        
        # 返回第一个找到的 .csproj.json 文件
        return csproj_files[0]
    
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
        # 查找 .csproj.json 文件
        csproj_json_path = self.find_csproj_json(project_name)
        
        if not csproj_json_path:
            raise FileNotFoundError(f"未找到项目 {project_name} 的 .csproj.json 文件")
        
        # 读取 .csproj.json 文件
        with open(csproj_json_path, 'r', encoding='utf-8') as f:
            csproj_data = json.load(f)
        
        # 提取资源
        resources = []
        root = csproj_data.get('root', {})
        self.extract_resources_from_node(root, resources)
        
        # 如果提供了项目路径，验证资源文件是否存在
        if project_path:
            project_path_obj = Path(project_path)
            for resource in resources:
                file_path = resource['file_path']
                # 处理 Windows 路径分隔符
                file_path = file_path.replace('\\', '/')
                full_path = project_path_obj / file_path
                resource['exists'] = full_path.exists()
                resource['absolute_path'] = str(full_path) if full_path.exists() else None
        
        # 分析每个资源被哪些页面引用
        self.logger.info("分析资源页面引用关系...")
        for resource in resources:
            referenced_by_pages = self._find_pages_using_resource(project_name, resource)
            resource['referenced_by_pages'] = referenced_by_pages
            resource['referenced_by_pages_count'] = len(referenced_by_pages)
            
            if referenced_by_pages:
                page_names = [p['page_name'] for p in referenced_by_pages]
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
            'project_name': project_name,
            'csproj_file': str(csproj_json_path.relative_to(self.output_base_dir)),
            'source_csproj': csproj_data.get('source_file', 'unknown'),
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
