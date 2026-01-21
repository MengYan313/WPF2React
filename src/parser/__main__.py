# -*- coding: utf-8 -*-
"""
解析器模块统一入口

使用方式：
    命令行：
        python -m src.parser <project_name>
    
    编程方式：
        from src.parser import __main__
        results = __main__.analyze_project("ExpenseItDemo")
        
        或
        
        from src.parser.__main__ import analyze_project
        results = analyze_project("ExpenseItDemo")
    
执行顺序：
    1. 解析 C# 文件
    2. 解析 XAML 文件
    3. 分析 C# 文件依赖关系
    4. 分析间接资源引用/依赖
    5. 分析页面依赖关系
    6. 分析资源依赖关系
    7. 分析控件依赖关系
"""

import sys
from pathlib import Path

from src.logger import get_logger
from .cs_parser import CsParser
from .xaml_parser import XamlParser
from .resource_dependency import ResourceDependencyAnalyzer
from .cs_dependency import CsDependencyAnalyzer
from .control_dependency import ControlDependencyAnalyzer
from .page_dependency import PageDependencyAnalyzer
from .indirect_resource_analysis import LayoutResourceDependencyAnalyzer


def analyze_project(
    project_name: str,
    output_base_dir: str = "outputs"
) -> dict:
    """
    分析整个项目：执行所有解析和依赖分析步骤
    
    执行顺序：
    1. 解析 C# 文件
    2. 解析 XAML 文件
    3. 分析 C# 文件依赖关系
    4. 分析间接资源引用/依赖
    5. 分析页面依赖关系
    6. 分析资源依赖关系
    7. 分析控件依赖关系
    
    Args:
        project_name: 项目名称（例如 "ExpenseItDemo"）
        output_base_dir: 输出基础目录（默认为 "outputs"）
    
    Returns:
        包含所有分析结果的字典
    """
    # 初始化日志
    logger = get_logger("parser")
    
    # 默认项目路径：repos/{project_name}
    project_path = f"repos/{project_name}"
    
    results = {
        "project_name": project_name,
        "project_path": project_path,
        "output_base_dir": output_base_dir,
        "steps": {}
    }
    
    logger.info("=" * 70)
    logger.info(f"开始分析项目: {project_name}")
    logger.info("=" * 70)
    
    # 步骤 1: 解析 C# 文件
    logger.info("\n[步骤 1/7] 解析 C# 文件...")
    try:
        cs_results = CsParser.parse_project(project_path, output_base_dir)
        results["steps"]["cs_parser"] = {
            "success": True,
            "files_parsed": len(cs_results),
            "results": cs_results
        }
        logger.info(f"✓ 成功解析 {len(cs_results)} 个 C# 文件")
    except Exception as e:
        results["steps"]["cs_parser"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ C# 解析失败: {e}")
        return results
    
    # 步骤 2: 解析 XAML 文件
    logger.info("\n[步骤 2/7] 解析 XAML 文件...")
    try:
        xaml_results = XamlParser.parse_project(project_path, output_base_dir, include_csproj=True)
        results["steps"]["xaml_parser"] = {
            "success": True,
            "files_parsed": len(xaml_results),
            "results": xaml_results
        }
        logger.info(f"✓ 成功解析 {len(xaml_results)} 个 XAML/CSPROJ 文件")
    except Exception as e:
        results["steps"]["xaml_parser"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ XAML 解析失败: {e}")
        return results
    
    # 步骤 3: 分析 C# 文件依赖关系
    logger.info("\n[步骤 3/7] 分析 C# 文件依赖关系...")
    try:
        cs_graph, cs_output_file = CsDependencyAnalyzer.analyze_project(
            project_name, output_base_dir
        )
        results["steps"]["cs_dependency"] = {
            "success": True,
            "output_file": cs_output_file,
            "total_files": cs_graph["total_files"],
            "migration_order": cs_graph["migration_order"]
        }
        logger.info(f"✓ C# 文件依赖分析完成: {cs_output_file}")
    except Exception as e:
        results["steps"]["cs_dependency"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ C# 文件依赖分析失败: {e}")
    
    # 步骤 4: 分析间接资源引用/依赖
    logger.info("\n[步骤 4/7] 分析间接资源引用/依赖...")
    try:
        indirect_result, indirect_output_file, data_resources_file, template_resources_file = LayoutResourceDependencyAnalyzer.analyze_project_static(
            project_name, output_base_dir
        )
        results["steps"]["indirect_resource_dependency"] = {
            "success": True,
            "output_file": indirect_output_file,
            "data_resources_file": data_resources_file,
            "template_resources_file": template_resources_file,
            "total_resources": indirect_result.get("total_resources", 0),
            "data_resources_count": len(indirect_result.get("resources", [])) if "resources" in indirect_result else 0
        }
        logger.info(f"✓ 间接资源引用/依赖分析完成:")
        logger.info(f"  - 间接资源: {indirect_output_file}")
        logger.info(f"  - 数据资源: {data_resources_file}")
        logger.info(f"  - 模板资源: {template_resources_file}")
    except Exception as e:
        results["steps"]["indirect_resource_dependency"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ 间接资源引用/依赖分析失败: {e}")
    
    # 步骤 5: 分析页面依赖关系
    logger.info("\n[步骤 5/7] 分析页面依赖关系...")
    try:
        page_graph, page_output_file = PageDependencyAnalyzer.analyze_project(
            project_name, output_base_dir
        )
        results["steps"]["page_dependency"] = {
            "success": True,
            "output_file": page_output_file,
            "total_pages": page_graph["total_pages"],
            "migration_order": page_graph["migration_order"]
        }
        logger.info(f"✓ 页面依赖分析完成: {page_output_file}")
    except Exception as e:
        results["steps"]["page_dependency"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ 页面依赖分析失败: {e}")
    
    # 步骤 6: 分析资源依赖关系
    logger.info("\n[步骤 6/7] 分析资源依赖关系...")
    try:
        resource_graph, resource_output_file = ResourceDependencyAnalyzer.analyze_project(
            project_name, project_path, output_base_dir
        )
        results["steps"]["resource_dependency"] = {
            "success": True,
            "output_file": resource_output_file,
            "total_resources": resource_graph.get("total_resources", 0)
        }
        logger.info(f"✓ 资源依赖分析完成: {resource_output_file}")
    except Exception as e:
        results["steps"]["resource_dependency"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ 资源依赖分析失败: {e}")
    
    # 步骤 7: 分析控件依赖关系
    logger.info("\n[步骤 7/7] 分析控件依赖关系...")
    try:
        control_results = ControlDependencyAnalyzer.analyze_project_static(
            project_name, output_base_dir
        )
        results["steps"]["control_dependency"] = {
            "success": True,
            "files_analyzed": len(control_results),
            "results": control_results
        }
        logger.info(f"✓ 控件依赖分析完成: {len(control_results)} 个文件")
    except Exception as e:
        results["steps"]["control_dependency"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"✗ 控件依赖分析失败: {e}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ 项目分析完成")
    logger.info("=" * 70)
    
    # 打印摘要
    logger.info("\n分析摘要:")
    for step_name, step_result in results["steps"].items():
        if step_result.get("success"):
            status = "✓"
            if step_name == "cs_parser":
                info = f"{step_result.get('files_parsed', 0)} 个文件"
            elif step_name == "xaml_parser":
                info = f"{step_result.get('files_parsed', 0)} 个文件"
            elif step_name == "resource_dependency":
                info = f"{step_result.get('total_resources', 0)} 个资源"
            elif step_name == "cs_dependency":
                info = f"{step_result.get('total_files', 0)} 个文件"
            elif step_name == "control_dependency":
                info = f"{step_result.get('files_analyzed', 0)} 个文件"
            elif step_name == "page_dependency":
                info = f"{step_result.get('total_pages', 0)} 个页面"
            elif step_name == "indirect_resource_dependency":
                info = f"{step_result.get('total_resources', 0)} 个资源"
            else:
                info = ""
            logger.info(f"  {status} {step_name}: {info}")
        else:
            logger.error(f"  ✗ {step_name}: 失败 - {step_result.get('error', 'Unknown error')}")
    
    return results


# python -m src.parser ExpenseItDemo
if __name__ == "__main__":
    logger = get_logger("parser")
    
    if len(sys.argv) < 2:
        logger.error("用法: python -m src.parser <project_name>")
        logger.error("示例: python -m src.parser ExpenseItDemo")
        sys.exit(1)
    
    project_name = sys.argv[1]
    
    try:
        results = analyze_project(project_name)
        
        # 检查是否有失败的步骤
        failed_steps = [
            name for name, result in results["steps"].items()
            if not result.get("success", False)
        ]
        
        if failed_steps:
            logger.warning(f"\n警告: {len(failed_steps)} 个步骤失败: {', '.join(failed_steps)}")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"\n✗ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

