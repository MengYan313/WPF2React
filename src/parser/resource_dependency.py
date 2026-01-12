# -*- coding: utf-8 -*-
"""
静态资源依赖关系识别模块
用于识别和定位 WPF 项目中的静态资源（如图片、字体、数据文件等）
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple


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
    
    def find_csproj_json(self, project_name: str) -> Optional[Path]:
        """
        查找项目的 .csproj.json 文件
        
        Args:
            project_name: 项目名称
            
        Returns:
            .csproj.json 文件路径，如果不存在返回 None
        """
        project_output_dir = self.output_base_dir / project_name
        
        if not project_output_dir.exists():
            return None
        
        # 查找 .csproj.json 文件
        csproj_files = list(project_output_dir.glob("*.csproj.json"))
        
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
                'missing_count': sum(1 for r in resources if r.get('exists') is False)
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
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径
        output_file = output_dir / "resource_dependency.json"
        
        # 保存为 JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.resources[project_name], f, ensure_ascii=False, indent=2)
        
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
            print(f"项目 {project_name} 的资源信息不存在")
            return
        
        result = self.resources[project_name]
        
        print("\n" + "=" * 70)
        print(f"项目: {result['project_name']}")
        print("=" * 70)
        print(f"源文件: {result['source_csproj']}")
        print(f"总资源数: {result['total_resources']}")
        print()
        
        if result['total_resources'] == 0:
            print("未找到任何资源文件")
            return
        
        # 按类型显示
        print("资源类型统计:")
        for res_type, count in result['summary']['by_type'].items():
            print(f"  {res_type}: {count} 个")
        
        print()
        
        # 按扩展名显示
        if result['summary']['by_extension']:
            print("文件类型统计:")
            for ext, count in result['summary']['by_extension'].items():
                ext_display = ext if ext else '(无扩展名)'
                print(f"  {ext_display}: {count} 个")
        
        print()
        
        # 显示资源列表
        print("资源列表:")
        print("-" * 70)
        for i, resource in enumerate(result['resources'], 1):
            print(f"\n{i}. {resource['file_name']}")
            print(f"   类型: {resource['resource_type']}")
            print(f"   路径: {resource['file_path']}")
            
            if 'exists' in resource:
                status = "✓ 存在" if resource['exists'] else "✗ 缺失"
                print(f"   状态: {status}")
            
            if 'link' in resource:
                print(f"   链接: {resource['link']}")
            
            if 'copy_to_output' in resource:
                print(f"   复制到输出: {resource['copy_to_output']}")
        
        print("\n" + "=" * 70)


# python -m src.parser.resource_dependency
if __name__ == "__main__":
    # from src.parser.resource_dependency import ResourceDependencyAnalyzer
    
    # 方式1：使用静态方法（推荐）
    result, output_file = ResourceDependencyAnalyzer.analyze_project(
        "ExpenseItDemo",
        "repos/ExpenseItDemo"
    )

    # 方式2：使用实例方法
    # analyzer = ResourceDependencyAnalyzer()
    # result = analyzer.analyze_project_resources("ExpenseItDemo", "repos/ExpenseItDemo")
    # output_file = analyzer.save_to_json("ExpenseItDemo")
    # analyzer.print_summary("ExpenseItDemo")  # 打印详细摘要

