"""
XML/XAML 文件解析器模块
用于解析 WPF 项目中的 XAML 和 CSPROJ 文件并提取其结构和内容
支持所有基于 XML 格式的文件
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from src.common.logging import get_logger
from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    mirrored_json_path,
    repository_relative_id,
)
from src.parser.io_utils import write_json
from src.parser.path_utils import discover_project_files

# 尝试导入 lxml（优先），否则使用标准 ElementTree
try:
    import lxml.etree as ET
    HAS_LXML = True
except ImportError:
    import xml.etree.ElementTree as ET
    HAS_LXML = False


@dataclass
class XamlNode:
    """XAML 节点数据类，表示解析后的单个元素"""
    
    tag: str  # 标签名（不含命名空间）
    full_tag: str  # 完整标签名（含命名空间）
    attributes: Dict[str, str] = field(default_factory=dict)  # 元素属性
    text: Optional[str] = None  # 文本内容
    children: List['XamlNode'] = field(default_factory=list)  # 子节点列表
    namespace: Optional[str] = None  # 命名空间 URI
    source_code: Optional[str] = None  # 原始 XAML 源代码（格式化后，适合 LLM 输入）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于序列化"""
        return {
            'tag': self.tag,
            'full_tag': self.full_tag,
            'attributes': self.attributes,
            'text': self.text,
            'namespace': self.namespace,
            'source_code': self.source_code,
            'children': [child.to_dict() for child in self.children]
        }


class XamlParser:
    """XML/XAML 文件解析器类，支持 .xaml 和 .csproj 等 XML 格式文件"""
    
    def __init__(self):
        # 初始化日志
        self.logger = get_logger("xaml_parser")
        
        self.namespaces: Dict[str, str] = {}  # 命名空间映射表
        self.root: Optional[XamlNode] = None  # 解析后的根节点
        self.source_file: Optional[str] = None  # 源文件路径
        self.source_id: Optional[str] = None  # 仓库相对 POSIX 路径唯一标识
        self.file_type: str = "else"  # 文件类型：page（有配对的 C# 文件）或 else
    
    def parse_file(self, file_path: str) -> XamlNode:
        """
        解析 XML 文件（支持 .xaml、.csproj 等）
        
        Args:
            file_path: XML 文件路径
            
        Returns:
            解析后的根节点
        """
        self.source_file = file_path  # 记录源文件路径
        
        # 判断文件类型（仅对 .xaml 文件判断）
        if file_path.endswith('.xaml'):
            self.file_type = self._determine_file_type(file_path)
        else:
            self.file_type = "else"
        
        # 解析 XML 文件
        if HAS_LXML:
            # 使用 lxml，保留原始格式
            parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False)
            tree = ET.parse(file_path, parser=parser)
        else:
            # 使用标准 ElementTree
            tree = ET.parse(file_path)
        
        root = tree.getroot()
        
        # 提取命名空间
        self._extract_namespaces(root)
        
        # 递归解析元素树（标记这是根元素）
        self.root = self._parse_element(root, is_root=True)
        
        # 特殊处理：如果根标签是 Application，则设置 type 为 root
        if self.root and self.root.tag.endswith('Application'):
            self.file_type = "root"
        
        return self.root
    
    def parse_string(self, xaml_content: str) -> XamlNode:
        """
        解析 XAML 字符串
        
        Args:
            xaml_content: XAML 内容字符串
            
        Returns:
            解析后的根节点
        """
        root = ET.fromstring(xaml_content)
        
        # 提取命名空间
        self._extract_namespaces(root)
        
        # 递归解析元素树（标记这是根元素）
        self.root = self._parse_element(root, is_root=True)
        return self.root
    
    def _determine_file_type(self, xaml_path: str) -> str:
        """
        判断 XAML 文件类型
        
        检查是否存在对应的 C# 代码文件（.xaml.cs 或 .cs）
        如果存在配对文件，则为 page；否则为 else
        
        Args:
            xaml_path: XAML 文件路径
            
        Returns:
            "page" 或 "else"
        """
        xaml_path_obj = Path(xaml_path)
        base_name = xaml_path_obj.stem  # 获取不含扩展名的文件名
        parent_dir = xaml_path_obj.parent
        
        # 检查是否存在 .xaml.cs 文件
        xaml_cs_path = parent_dir / f"{base_name}.xaml.cs"
        if xaml_cs_path.exists():
            return "page"
        
        # 检查是否存在 .cs 文件
        cs_path = parent_dir / f"{base_name}.cs"
        if cs_path.exists():
            return "page"
        
        return "else"
    
    def _format_source_code_for_llm(self, source_code: str, is_root: bool = False) -> str:
        """
        格式化源代码使其适合作为 LLM 输入
        
        处理策略：
        1. 使用 lxml 时：保留原始的命名空间前缀（xmlns, x:, local: 等）
        2. 使用 ElementTree 时：简化自动生成的 ns0:, ns1: 等前缀
        3. 保留结构和缩进，便于 LLM 理解层次
        4. 去除多余的空白行
        5. 统一使用 2 个空格缩进
        6. 去除行尾空白
        7. 对于子元素（非根元素），移除继承的命名空间声明
        
        Args:
            source_code: 原始 XML 源代码
            is_root: 是否为根元素（根元素保留 xmlns 声明，子元素移除）
            
        Returns:
            格式化后的源代码
        """
        if not source_code:
            return ""
        
        import re
        
        # 仅当使用 ElementTree 时（lxml 不可用），才需要简化自动生成的前缀
        if not HAS_LXML and ('ns0:' in source_code or 'ns1:' in source_code):
            # 简化命名空间前缀
            # 将 ns0:Tag 简化为 Tag（ns0 通常是默认的 WPF 命名空间）
            source_code = re.sub(r'<ns0:', '<', source_code)
            source_code = re.sub(r'</ns0:', '</', source_code)
            source_code = re.sub(r'<ns1:', '<x:', source_code)
            source_code = re.sub(r'</ns1:', '</x:', source_code)
            source_code = re.sub(r'<ns2:', '<', source_code)
            source_code = re.sub(r'</ns2:', '</', source_code)
            
            # 移除自动生成的 xmlns 命名空间声明
            source_code = re.sub(r'\s+xmlns:ns\d+="[^"]*"', '', source_code)
        
        # 对于非根元素，移除所有的 xmlns 命名空间声明
        # 因为这些声明已经在根元素中定义，子元素不需要重复
        if not is_root:
            # 移除 xmlns="..." 和 xmlns:prefix="..." 声明
            source_code = re.sub(r'\s+xmlns(?::[a-zA-Z_][\w.-]*)?="[^"]*"', '', source_code)
        
        # 处理行格式
        lines = source_code.split('\n')
        formatted_lines = []
        
        for line in lines:
            # 去除行尾空白
            line = line.rstrip()
            
            # 跳过空行
            if not line.strip():
                continue
            
            stripped = line.lstrip()
            
            if stripped:
                # 计算原始缩进
                indent_count = len(line) - len(line.lstrip())
                # 标准化为 2 个空格的倍数
                normalized_indent = (indent_count // 2) * 2
                formatted_line = ' ' * normalized_indent + stripped
                formatted_lines.append(formatted_line)
        
        # 合并行，确保最后没有多余的换行
        result = '\n'.join(formatted_lines)
        
        return result
    
    def _extract_namespaces(self, element: Any) -> None:
        """提取所有命名空间声明"""
        # 遍历整个树，收集所有命名空间
        for elem in element.iter():
            # 只处理元素节点
            if not isinstance(elem.tag, str):
                continue
            
            # 从标签中提取命名空间
            if elem.tag.startswith('{'):
                ns_uri = elem.tag[1:].split('}')[0]
                if ns_uri not in self.namespaces.values():
                    # 为未命名的命名空间生成前缀
                    prefix = f"ns{len(self.namespaces)}"
                    self.namespaces[prefix] = ns_uri
            
            # 从属性中提取命名空间声明
            for attr_name, attr_value in elem.attrib.items():
                if attr_name.startswith('{http://www.w3.org/2000/xmlns/}'):
                    prefix = attr_name.split('}')[1]
                    self.namespaces[prefix] = attr_value
                elif attr_name == 'xmlns':
                    self.namespaces['default'] = attr_value
    
    def _parse_element(self, element: Any, is_root: bool = False) -> XamlNode:
        """
        递归解析单个元素及其子元素
        
        Args:
            element: Element 对象（lxml 或 ElementTree）
            is_root: 是否为根元素（影响命名空间声明的保留）
            
        Returns:
            解析后的 XamlNode 对象
        """
        # 提取标签名和命名空间
        full_tag = element.tag
        namespace = None
        tag = full_tag
        
        # 处理带命名空间的标签
        if full_tag.startswith('{'):
            namespace, tag = full_tag[1:].split('}', 1)
        
        # 提取属性（移除命名空间前缀）
        attributes = {}
        for attr_name, attr_value in element.attrib.items():
            # 跳过 xmlns 声明
            if attr_name.startswith('{http://www.w3.org/2000/xmlns/}') or attr_name == 'xmlns':
                continue
            
            # 处理带命名空间的属性名
            clean_attr_name = attr_name
            if attr_name.startswith('{'):
                _, clean_attr_name = attr_name[1:].split('}', 1)
            
            attributes[clean_attr_name] = attr_value
        
        # 提取文本内容（去除前后空白，空白字符视为无内容）
        text = None
        if element.text:
            stripped = element.text.strip()
            text = stripped if stripped else None
        
        # 提取源代码并格式化（适合 LLM 输入）
        source_code = None
        try:
            # 使用 tostring 获取元素的 XML 表示
            # lxml 会保留原始的命名空间前缀，ElementTree 会生成 ns0, ns1 等
            raw_source = ET.tostring(element, encoding='unicode', method='xml')
            
            if raw_source:
                # 格式化源代码（根元素保留 xmlns，子元素移除 xmlns）
                source_code = self._format_source_code_for_llm(raw_source, is_root=is_root)
        except Exception:
            # 如果提取失败，保持为 None
            pass
        
        # 创建节点对象
        node = XamlNode(
            tag=tag,
            full_tag=full_tag,
            attributes=attributes,
            text=text,
            namespace=namespace,
            source_code=source_code
        )
        
        # 递归解析子元素（子元素标记为非根元素）
        for child in element:
            # 只处理元素节点（跳过注释、文本节点等）
            if isinstance(child.tag, str):  # Element 的 tag 是字符串
                child_node = self._parse_element(child, is_root=False)
                node.children.append(child_node)
        
        return node
    
    def get_elements_by_tag(self, tag_name: str, node: Optional[XamlNode] = None) -> List[XamlNode]:
        """
        根据标签名查找所有匹配的元素
        
        Args:
            tag_name: 要查找的标签名
            node: 起始节点（默认从根节点开始）
            
        Returns:
            匹配的节点列表
        """
        if node is None:
            node = self.root
        
        if node is None:
            return []
        
        results = []
        
        # 检查当前节点
        if node.tag == tag_name:
            results.append(node)
        
        # 递归检查子节点
        for child in node.children:
            results.extend(self.get_elements_by_tag(tag_name, child))
        
        return results
    
    def print_tree(self, node: Optional[XamlNode] = None, indent: int = 0) -> None:
        """
        打印元素树结构（用于调试）
        
        Args:
            node: 起始节点（默认从根节点开始）
            indent: 缩进级别
        """
        if node is None:
            node = self.root
        
        if node is None:
            return
        
        # 打印当前节点信息
        indent_str = "  " * indent
        attrs_str = " ".join(f'{k}="{v}"' for k, v in list(node.attributes.items())[:3])
        if len(node.attributes) > 3:
            attrs_str += " ..."
        
        self.logger.debug(f"{indent_str}<{node.tag} {attrs_str}>")
        
        # 打印文本内容
        if node.text:
            text_preview = node.text[:50] + "..." if len(node.text) > 50 else node.text
            self.logger.debug(f"{indent_str}  Text: {text_preview}")
        
        # 递归打印子节点
        for child in node.children:
            self.print_tree(child, indent + 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将解析结果转换为字典格式
        
        Returns:
            包含完整解析结果的字典
        """
        return {
            'id_scheme': SOURCE_ID_SCHEME,
            'source_id': self.source_id,
            'source_file': self.source_file,
            'type': self.file_type,
            'namespaces': self.namespaces,
            'root': self.root.to_dict() if self.root else None
        }
    
    def save_to_json(self, output_path: str, indent: int = 2) -> None:
        """
        将解析结果保存为 JSON 文件
        
        Args:
            output_path: 输出 JSON 文件路径
            indent: JSON 缩进空格数（默认为2）
        """
        if self.root is None:
            raise ValueError("没有可保存的解析结果，请先调用 parse_file 或 parse_string")

        write_json(output_path, self.to_dict(), indent=indent)
    
    @staticmethod
    def parse_project(project_path: str, output_base_dir: str = "outputs", 
                     include_csproj: bool = True) -> Dict[str, str]:
        """
        解析项目中所有 XML 文件（XAML 和 CSPROJ）并保存为 JSON 格式
        
        Args:
            project_path: 项目路径（例如 "repos/ExpenseItDemo"）
            output_base_dir: 输出基础目录（默认为 "outputs"）
            include_csproj: 是否包含 .csproj 文件（默认为 True）
            
        Returns:
            字典，键为 XML 文件路径，值为对应的 JSON 输出路径
        """
        project_path = Path(project_path)
        
        if not project_path.exists():
            raise FileNotFoundError(f"项目路径不存在: {project_path}")
        
        # 获取项目名称
        project_name = project_path.name
        
        # 创建输出目录：outputs/{project_name}/xaml/
        output_dir = Path(output_base_dir) / project_name / "xaml"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找所有 XAML 文件
        xaml_files = discover_project_files(project_path, [".xaml"])
        
        # 查找所有 CSPROJ 文件
        csproj_files = []
        if include_csproj:
            csproj_files = discover_project_files(project_path, [".csproj"])
        
        # 合并文件列表
        all_files = xaml_files + csproj_files
        
        # 初始化日志
        logger = get_logger("xaml_parser")
        
        if not all_files:
            logger.warning(f"在 {project_path} 中未找到 XAML 或 CSPROJ 文件")
            return {}
        
        results = {}
        success_count = 0
        error_count = 0
        
        logger.info(f"开始解析项目: {project_name}")
        logger.info(f"找到 {len(xaml_files)} 个 XAML 文件")
        if include_csproj:
            logger.info(f"找到 {len(csproj_files)} 个 CSPROJ 文件")
        logger.debug("-" * 70)
        
        for xml_file in all_files:
            try:
                # 创建解析器实例
                parser = XamlParser()
                
                # 解析 XML 文件
                parser.parse_file(str(xml_file))
                parser.source_id = repository_relative_id(xml_file, project_path)
                
                # 镜像仓库相对目录，避免同名文件互相覆盖。
                output_file = mirrored_json_path(output_dir, parser.source_id)
                
                # 保存为 JSON
                parser.save_to_json(str(output_file))
                
                results[str(xml_file)] = str(output_file)
                success_count += 1
                
                # 显示文件类型标识
                file_type = "CSPROJ" if xml_file.suffix == ".csproj" else "XAML"
                logger.info(f"✓ [{file_type:7}] {xml_file.name} -> {output_file.relative_to(output_base_dir)}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"✗ {xml_file.name}: 解析失败 - {str(e)}")
        
        logger.debug("-" * 70)
        logger.info(f"解析完成: 成功 {success_count} 个, 失败 {error_count} 个")
        logger.info(f"输出目录: {output_dir}")
        
        return results


# 运行示例：python -m src.parser.xaml_parser
if __name__ == "__main__":
    # 导入示例：from src.parser.xaml_parser import XamlParser

    # 方式1：解析单个 XAML 文件
    # 示例：parser = XamlParser()
    # 示例：parser.parse_file("repos/ExpenseItDemo/MainWindow.xaml")
    # 示例：parser.save_to_json("outputs/test/MainWindow.xaml.json")

    # 方式2：解析单个 CSPROJ 文件
    # 示例：parser = XamlParser()
    # 示例：parser.parse_file("repos/ExpenseItDemo/ExpenseItDemo.csproj")
    # 示例：parser.save_to_json("outputs/test/ExpenseItDemo.csproj.json")

    # 方式3：批量解析整个项目（包含 XAML 和 CSPROJ）
    results = XamlParser.parse_project("repos/ExpenseItDemo", include_csproj=True)
