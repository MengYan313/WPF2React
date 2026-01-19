"""
解析器模块

提供 WPF 项目解析和依赖分析功能：
- 文件解析：C# 文件解析、XAML 文件解析
- 依赖分析：页面依赖、C# 文件依赖、控件依赖、资源依赖
- 统一入口：analyze_project 函数，按顺序执行所有解析和依赖分析步骤
"""

# 统一入口函数
from .__main__ import analyze_project

__all__ = [
    'analyze_project',  # 统一入口函数
]
