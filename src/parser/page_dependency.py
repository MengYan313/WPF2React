# -*- coding: utf-8 -*-
"""
页面级（文件级）依赖关系识别模块
用于分析 WPF 项目中页面之间的依赖和跳转关系

本模块通过读取 XAML 和 CS 解析器的输出 (JSON 文件)，
自动识别有效页面 (type=page)，然后分析页面之间的依赖关系。

工作流程:
1. 读取 outputs/{project_name}/cs/*.json 文件
2. 检查 type 字段，找出所有 type=page 的文件
3. 从 source_file 字段获取原始 CS 文件路径
4. 匹配对应的 XAML 文件
5. 分析 CS 代码中的页面依赖关系
6. 生成依赖图并保存为 JSON
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


class PageDependencyAnalyzer:
    """页面依赖关系分析器"""
    
    def __init__(self, project_name: str, output_base_dir: str = "outputs"):
        """
        初始化分析器
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录（默认为 "outputs"）
        """
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        self.cs_output_dir = self.output_base_dir / project_name / "cs"
        self.xaml_output_dir = self.output_base_dir / project_name / "xaml"
        self.valid_pages: Dict[str, Dict[str, str]] = {}  # {页面名: {xaml: 路径, cs: 路径}}
        self.dependencies: Dict[str, List[str]] = {}  # {页面名: [依赖的页面列表]}
    
    def find_valid_pages(self) -> Dict[str, Dict[str, str]]:
        """
        查找所有有效页面
        
        通过读取 outputs/{project_name}/cs/ 目录下的 JSON 文件
        检查 type 字段是否为 "page" 来判断有效页面
        
        Returns:
            字典，键为页面名，值为包含 xaml 和 cs 路径的字典
        """
        if not self.cs_output_dir.exists():
            raise FileNotFoundError(f"CS 输出目录不存在: {self.cs_output_dir}\n请先运行 CS 和 XAML 解析器")
        
        if not self.xaml_output_dir.exists():
            raise FileNotFoundError(f"XAML 输出目录不存在: {self.xaml_output_dir}\n请先运行 CS 和 XAML 解析器")
        
        valid_pages = {}
        
        # 遍历所有 CS JSON 文件
        for cs_json_file in self.cs_output_dir.glob("*.cs.json"):
            try:
                # 读取 JSON 文件
                with open(cs_json_file, 'r', encoding='utf-8') as f:
                    cs_data = json.load(f)
                
                # 检查 type 字段是否为 "page"
                if cs_data.get('type') != 'page':
                    continue
                
                # 获取源文件路径
                cs_source_file = cs_data.get('source_file')
                if not cs_source_file:
                    continue
                
                # 提取页面名（去掉扩展名）
                # MainWindow.cs 或 MainWindow.xaml.cs -> MainWindow
                cs_filename = Path(cs_source_file).name
                if cs_filename.endswith('.xaml.cs'):
                    page_name = cs_filename[:-8]  # 去掉 .xaml.cs
                elif cs_filename.endswith('.cs'):
                    page_name = cs_filename[:-3]  # 去掉 .cs
                else:
                    continue
                
                # 查找对应的 XAML JSON 文件
                xaml_json_file = self.xaml_output_dir / f"{page_name}.xaml.json"
                if not xaml_json_file.exists():
                    continue
                
                # 读取 XAML JSON 文件获取源文件路径
                with open(xaml_json_file, 'r', encoding='utf-8') as f:
                    xaml_data = json.load(f)
                
                xaml_source_file = xaml_data.get('source_file')
                if not xaml_source_file:
                    continue
                
                # 验证 XAML 文件的 type 也是 page（双重确认）
                if xaml_data.get('type') != 'page':
                    continue
                
                # 记录有效页面
                valid_pages[page_name] = {
                    'xaml': xaml_source_file,
                    'cs': cs_source_file
                }
                
            except Exception as e:
                print(f"警告: 处理文件 {cs_json_file.name} 时出错: {e}")
                continue
        
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
                'xaml_file': files['xaml'],
                'cs_file': files['cs'],
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
            'total_pages': len(self.valid_pages),
            'pages': pages_info,
            'dependency_summary': {
                'total_dependencies': sum(len(deps) for deps in self.dependencies.values()),
                'pages_with_dependencies': sum(1 for deps in self.dependencies.values() if deps),
                'isolated_pages': sum(1 for deps in self.dependencies.values() if not deps)
            }
        }
        
        return dependency_graph
    
    def save_to_json(self) -> str:
        """
        将依赖关系保存为 JSON 文件
            
        Returns:
            输出文件的完整路径
        """
        # 生成依赖图
        dependency_graph = self.generate_dependency_graph()
        
        # 创建输出目录：outputs/{project_name}/dependency/
        output_path = self.output_base_dir / self.project_name / "dependency"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径
        output_file = output_path / "page_dependency.json"
        
        # 保存为 JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(dependency_graph, f, ensure_ascii=False, indent=2)
        
        return str(output_file)
    
    @staticmethod
    def analyze_project(project_name: str, output_dir: str = "outputs") -> Tuple[Dict, str]:
        """
        分析项目并保存依赖关系（静态方法，便于调用）
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_dir: 输出目录
            
        Returns:
            (依赖图字典, 输出文件路径)
        """
        analyzer = PageDependencyAnalyzer(project_name, output_dir)
        
        # 查找有效页面
        valid_pages = analyzer.find_valid_pages()
        print(f"项目: {analyzer.project_name}")
        print(f"找到 {len(valid_pages)} 个有效页面（type=page）")
        
        # 分析依赖关系
        dependencies = analyzer.analyze_dependencies()
        
        # 保存结果
        output_file = analyzer.save_to_json()
        
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
            print(f"    XAML: {files['xaml']}")
            print(f"    CS:   {files['cs']}")
        
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
    graph, output_file = PageDependencyAnalyzer.analyze_project("ExpenseItDemo")
    
    print("\n" + "=" * 70)
    print("✅ 页面依赖分析完成")
    print("=" * 70)
    print(f"\n输出文件: {output_file}")
    print(f"\n总页面数: {graph['total_pages']}")
    print(f"总依赖数: {graph['dependency_summary']['total_dependencies']}")
    print(f"有依赖的页面: {graph['dependency_summary']['pages_with_dependencies']}")
    print(f"独立页面: {graph['dependency_summary']['isolated_pages']}")
    print("\n" + "=" * 70)

    # 方式2：使用实例方法
    # analyzer = PageDependencyAnalyzer("ExpenseItDemo")
    # valid_pages = analyzer.find_valid_pages()
    # dependencies = analyzer.analyze_dependencies()
    # output_file = analyzer.save_to_json()

