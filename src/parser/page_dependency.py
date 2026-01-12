# -*- coding: utf-8 -*-
"""
页面级（文件级）依赖关系识别模块
用于分析 WPF 项目中页面之间的依赖和跳转关系
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


class PageDependencyAnalyzer:
    """页面依赖关系分析器"""
    
    def __init__(self, project_path: str):
        """
        初始化分析器
        
        Args:
            project_path: 项目路径（例如 "repos/ExpenseItDemo"）
        """
        self.project_path = Path(project_path)
        self.project_name = self.project_path.name
        self.valid_pages: Dict[str, Dict[str, str]] = {}  # {页面名: {xaml: 路径, cs: 路径}}
        self.dependencies: Dict[str, List[str]] = {}  # {页面名: [依赖的页面列表]}
    
    def find_valid_pages(self) -> Dict[str, Dict[str, str]]:
        """
        查找所有有效页面
        
        有效页面的条件：
        1. 同时存在 .xaml 和 .cs 文件（或 .xaml.cs）
        2. 前缀相同
        3. 不是 App 开头的文件
        
        Returns:
            字典，键为页面名，值为包含 xaml 和 cs 路径的字典
        """
        if not self.project_path.exists():
            raise FileNotFoundError(f"项目路径不存在: {self.project_path}")
        
        # 查找所有 .xaml 文件（不包括 App.xaml）
        xaml_files = {}
        for xaml_file in self.project_path.rglob("*.xaml"):
            # 获取相对路径和文件名
            relative_path = xaml_file.relative_to(self.project_path)
            page_name = xaml_file.stem  # 不含扩展名的文件名
            
            # 排除 App 开头的文件
            if page_name.startswith("App"):
                continue
            
            xaml_files[page_name] = str(xaml_file)
        
        # 对每个 .xaml 文件，查找对应的 .cs 或 .xaml.cs 文件
        valid_pages = {}
        for page_name, xaml_path in xaml_files.items():
            xaml_path_obj = Path(xaml_path)
            parent_dir = xaml_path_obj.parent
            
            # 查找对应的 .cs 文件
            # 优先查找 .xaml.cs，其次查找 .cs
            cs_path = None
            xaml_cs_path = parent_dir / f"{page_name}.xaml.cs"
            normal_cs_path = parent_dir / f"{page_name}.cs"
            
            if xaml_cs_path.exists():
                cs_path = str(xaml_cs_path)
            elif normal_cs_path.exists():
                cs_path = str(normal_cs_path)
            
            # 如果找到对应的 .cs 文件，则为有效页面
            if cs_path:
                valid_pages[page_name] = {
                    'xaml': xaml_path,
                    'cs': cs_path
                }
        
        self.valid_pages = valid_pages
        return valid_pages
    
    def remove_comments(self, code: str) -> str:
        """
        移除 C# 代码中的注释
        
        Args:
            code: C# 源代码
            
        Returns:
            移除注释后的代码
        """
        # 移除单行注释 //
        code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
        
        # 移除多行注释 /* */
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        return code
    
    def analyze_dependencies(self) -> Dict[str, List[str]]:
        """
        分析所有有效页面的依赖关系
        
        在每个页面的 .cs 文件中搜索其他页面的名称
        如果找到，则认为当前页面依赖该页面
        
        Returns:
            字典，键为页面名，值为依赖的页面列表
        """
        if not self.valid_pages:
            self.find_valid_pages()
        
        dependencies = {}
        page_names = set(self.valid_pages.keys())
        
        for current_page, files in self.valid_pages.items():
            cs_file = files['cs']
            
            # 读取 .cs 文件内容
            try:
                with open(cs_file, 'r', encoding='utf-8') as f:
                    code = f.read()
            except UnicodeDecodeError:
                # 尝试其他编码
                with open(cs_file, 'r', encoding='latin-1') as f:
                    code = f.read()
            
            # 移除注释
            code_without_comments = self.remove_comments(code)
            
            # 搜索其他页面的名称
            page_dependencies = []
            for other_page in page_names:
                if other_page == current_page:
                    continue
                
                # 使用正则表达式搜索页面名称
                # 匹配 new PageName() 或 new PageName { 这样的模式
                pattern = r'\bnew\s+' + re.escape(other_page) + r'\s*[({]'
                
                if re.search(pattern, code_without_comments):
                    page_dependencies.append(other_page)
            
            dependencies[current_page] = sorted(page_dependencies)
        
        self.dependencies = dependencies
        return dependencies
    
    def generate_dependency_graph(self) -> Dict[str, any]:
        """
        生成依赖关系图的完整数据结构
        
        Returns:
            包含项目信息、页面列表和依赖关系的字典
        """
        if not self.dependencies:
            self.analyze_dependencies()
        
        # 构建页面详细信息
        pages_info = {}
        for page_name, files in self.valid_pages.items():
            pages_info[page_name] = {
                'xaml_file': str(Path(files['xaml']).relative_to(self.project_path)),
                'cs_file': str(Path(files['cs']).relative_to(self.project_path)),
                'dependencies': self.dependencies.get(page_name, []),
                'dependency_count': len(self.dependencies.get(page_name, []))
            }
        
        # 计算被依赖次数
        depended_by_count = {page: 0 for page in self.valid_pages.keys()}
        for deps in self.dependencies.values():
            for dep in deps:
                depended_by_count[dep] += 1
        
        # 添加被依赖信息
        for page_name in pages_info:
            pages_info[page_name]['depended_by_count'] = depended_by_count[page_name]
        
        # 构建完整的依赖图
        dependency_graph = {
            'project_name': self.project_name,
            'project_path': str(self.project_path),
            'total_pages': len(self.valid_pages),
            'pages': pages_info,
            'dependency_summary': {
                'total_dependencies': sum(len(deps) for deps in self.dependencies.values()),
                'pages_with_dependencies': sum(1 for deps in self.dependencies.values() if deps),
                'isolated_pages': sum(1 for deps in self.dependencies.values() if not deps)
            }
        }
        
        return dependency_graph
    
    def save_to_json(self, output_dir: str = "outputs") -> str:
        """
        将依赖关系保存为 JSON 文件
        
        Args:
            output_dir: 输出基础目录（默认为 "outputs"）
            
        Returns:
            输出文件的完整路径
        """
        # 生成依赖图
        dependency_graph = self.generate_dependency_graph()
        
        # 创建输出目录：outputs/{project_name}/dependency/
        output_path = Path(output_dir) / self.project_name / "dependency"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径
        output_file = output_path / "page_dependency.json"
        
        # 保存为 JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(dependency_graph, f, ensure_ascii=False, indent=2)
        
        return str(output_file)
    
    @staticmethod
    def analyze_project(project_path: str, output_dir: str = "outputs") -> Tuple[Dict, str]:
        """
        分析项目并保存依赖关系（静态方法，便于调用）
        
        Args:
            project_path: 项目路径
            output_dir: 输出目录
            
        Returns:
            (依赖图字典, 输出文件路径)
        """
        analyzer = PageDependencyAnalyzer(project_path)
        
        # 查找有效页面
        valid_pages = analyzer.find_valid_pages()
        print(f"项目: {analyzer.project_name}")
        print(f"找到 {len(valid_pages)} 个有效页面")
        
        # 分析依赖关系
        dependencies = analyzer.analyze_dependencies()
        
        # 保存结果
        output_file = analyzer.save_to_json(output_dir)
        
        return analyzer.generate_dependency_graph(), output_file
    
    def print_summary(self):
        """打印依赖关系摘要"""
        if not self.dependencies:
            self.analyze_dependencies()
        
        print("\n" + "=" * 70)
        print(f"项目: {self.project_name}")
        print("=" * 70)
        print(f"\n有效页面数: {len(self.valid_pages)}")
        print("\n页面列表:")
        for page_name, files in sorted(self.valid_pages.items()):
            print(f"  - {page_name}")
            print(f"    XAML: {Path(files['xaml']).relative_to(self.project_path)}")
            print(f"    CS:   {Path(files['cs']).relative_to(self.project_path)}")
        
        print("\n" + "-" * 70)
        print("依赖关系:")
        print("-" * 70)
        
        for page, deps in sorted(self.dependencies.items()):
            if deps:
                print(f"\n  {page} →")
                for dep in deps:
                    print(f"    - {dep}")
            else:
                print(f"\n  {page} (无依赖)")
        
        print("\n" + "=" * 70)


# python -m src.parser.page_dependency
if __name__ == "__main__":
    # from src.parser.page_dependency import PageDependencyAnalyzer

    # 方式1：使用静态方法（推荐）
    graph, output_file = PageDependencyAnalyzer.analyze_project("repos/ExpenseItDemo")

    # 方式2：使用实例方法
    # analyzer = PageDependencyAnalyzer("repos/ExpenseItDemo")
    # valid_pages = analyzer.find_valid_pages()
    # dependencies = analyzer.analyze_dependencies()
    # output_file = analyzer.save_to_json()

