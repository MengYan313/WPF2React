# -*- coding: utf-8 -*-
"""
控件依赖关系识别模块
用于从 XAML JSON 文件中提取 WPF 基础控件及其层级结构
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.logger import get_logger
from .wpf_base_controls import WPF_BASE_CONTROLS, is_wpf_base_control


class ControlDependencyAnalyzer:
    """控件依赖关系分析器"""
    
    def __init__(self, output_base_dir: str = "outputs"):
        """
        初始化分析器
        
        Args:
            output_base_dir: 输出基础目录（默认为 "outputs"）
        """
        self.output_base_dir = Path(output_base_dir)
        self.control_dependencies: Dict[str, Dict[str, Any]] = {}  # {文件名: 控件依赖信息}
        
        # 初始化日志
        self.logger = get_logger("control_dependency")
    
    def extract_controls_from_node(self, node: Dict[str, Any], parent_tag: str = '') -> Optional[Dict[str, Any]]:
        """
        从节点中提取控件信息（递归）
        
        只保留 WPF 基础控件节点，非控件容器节点会被移除，其子节点会向上提升
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
        
        # 检查当前节点是否是 WPF 基础控件
        is_control = is_wpf_base_control(tag)
        
        # 递归处理子节点，收集所有控件子节点
        control_children = []
        for child in node.get('children', []):
            extracted = self.extract_controls_from_node(child, parent_tag=tag)
            if extracted:
                # 如果返回的是列表（子节点提升），展开添加
                if isinstance(extracted, list):
                    control_children.extend(extracted)
                else:
                    control_children.append(extracted)
        
        # 如果当前节点是控件，保留此节点
        if is_control:
            result = {
                'tag': tag,
                'source_code': node.get('source_code', ''),
                'attributes': node.get('attributes', {}),
                'data_template': '',  # 数据模板字段，预留供后续使用
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
    
    def analyze_xaml_file(self, xaml_json_path: str) -> Dict[str, Any]:
        """
        分析单个 XAML JSON 文件，提取控件依赖
        
        Args:
            xaml_json_path: XAML JSON 文件路径
            
        Returns:
            控件依赖信息字典
        """
        # 读取 XAML JSON 文件
        with open(xaml_json_path, 'r', encoding='utf-8') as f:
            xaml_data = json.load(f)
        
        # 提取基本信息
        source_file = xaml_data.get('source_file', '')
        namespaces = xaml_data.get('namespaces', {})
        root = xaml_data.get('root', {})
        root_tag = root.get('tag', 'Root')  # 获取根节点的 tag
        
        # 提取控件信息
        controls_root = self.extract_controls_from_node(root)
        
        # 处理返回列表的情况（根节点不是控件，多个子节点被提升）
        if isinstance(controls_root, list):
            # 如果返回列表，需要包装为根节点
            if len(controls_root) == 1:
                controls_root = controls_root[0]
            else:
                # 使用原始根节点的 tag 创建包装节点
                controls_root = {
                    'tag': root_tag,  # 使用原始根节点的 tag（如 Window）
                    'source_code': root.get('source_code', ''),
                    'attributes': root.get('attributes', {}),
                    'data_template': '',
                    'children': controls_root
                }
        
        # 统计控件数量
        control_count = self._count_controls(controls_root)
        
        # 构建结果
        result = {
            'source_file': source_file,
            'xaml_json_file': xaml_json_path,
            'namespaces': namespaces,
            'control_count': control_count,
            'controls': controls_root
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
            xaml_filename: XAML 文件名（如 "MainWindow.xaml"）
            project_name: 项目名称
            output_dir: 输出目录（如果为 None，则使用 outputs/{project_name}/dependency）
            
        Returns:
            输出文件的完整路径
        """
        if output_dir is None:
            output_dir = self.output_base_dir / project_name / "dependency"
        else:
            output_dir = Path(output_dir)
        
        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成输出文件名：control_{filename}.json
        # 移除 .xaml 后缀，添加 control_ 前缀
        base_name = xaml_filename.replace('.xaml', '')
        output_filename = f"control_{base_name}.json"
        output_file = output_dir / output_filename
        
        # 获取控件依赖信息
        if xaml_filename not in self.control_dependencies:
            raise ValueError(f"未找到文件 {xaml_filename} 的控件依赖信息")
        
        # 保存为 JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.control_dependencies[xaml_filename], f, 
                     ensure_ascii=False, indent=2)
        
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
            f for f in xaml_json_dir.glob("*.xaml.json")
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
        
        for xaml_json_file in xaml_json_files:
            try:
                # 提取 XAML 文件名
                xaml_filename = xaml_json_file.name.replace('.json', '')
                
                # 读取 JSON 文件检查 type 字段
                with open(xaml_json_file, 'r', encoding='utf-8') as f:
                    xaml_data = json.load(f)
                
                file_type = xaml_data.get('type', 'unknown')
                
                # 只处理 type=page 的文件
                if file_type != 'page':
                    skipped_count += 1
                    print(f"- {xaml_filename:40} (跳过: type={file_type})")
                    continue
                
                # 分析控件依赖
                control_dep = self.analyze_xaml_file(str(xaml_json_file))
                self.control_dependencies[xaml_filename] = control_dep
                
                # 保存结果
                output_file = self.save_to_json(xaml_filename, project_name)
                
                results[xaml_filename] = output_file
                success_count += 1
                
                # 输出信息
                control_count = control_dep.get('control_count', 0)
                logger.info(f"✓ {xaml_filename:40} -> {control_count:3} 个控件 (type=page)")
                
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


# python -m src.parser.control_dependency
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
