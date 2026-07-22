"""
C# 代码解析器模块
用于解析 WPF 项目中的 C# 文件并提取其结构和内容
使用 tree-sitter 进行语法树解析
"""

# 注意：必须延迟注解求值。否则当 tree-sitter 未安装时，
# `from tree_sitter import Node` 失败会导致 `def _get_text(self, node: Node)`
# 这类注解在类定义阶段抛出 NameError，使 HAS_TREE_SITTER 的降级逻辑形同虚设。
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from src.common.logging import get_logger
from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    mirrored_json_path,
    repository_relative_id,
)
from src.parser.io_utils import write_json
from src.parser.path_utils import discover_project_files

try:
    import tree_sitter_c_sharp as tscsharp
    from tree_sitter import Language, Parser, Node
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False
    logger = get_logger("cs_parser")
    logger.warning("tree-sitter 或 tree-sitter-c-sharp 未安装，C# 解析功能不可用")


@dataclass
class CsNode:
    """C# 语法树节点数据类，表示解析后的代码元素"""
    
    node_type: str  # 节点类型（class, method, property, field 等）
    name: Optional[str] = None  # 元素名称
    modifiers: List[str] = field(default_factory=list)  # 修饰符（public, private, static 等）
    return_type: Optional[str] = None  # 返回类型（用于方法）
    data_type: Optional[str] = None  # 数据类型（用于字段和属性）
    parameters: List[Dict[str, str]] = field(default_factory=list)  # 参数列表
    base_types: List[str] = field(default_factory=list)  # 基类和接口
    attributes: List[str] = field(default_factory=list)  # 特性（Attribute）
    source_code: Optional[str] = None  # 原始源代码
    start_line: int = 0  # 起始行号
    end_line: int = 0  # 结束行号
    children: List['CsNode'] = field(default_factory=list)  # 子节点列表
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于序列化"""
        return {
            'node_type': self.node_type,
            'name': self.name,
            'modifiers': self.modifiers,
            'return_type': self.return_type,
            'data_type': self.data_type,
            'parameters': self.parameters,
            'base_types': self.base_types,
            'attributes': self.attributes,
            'source_code': self.source_code,
            'start_line': self.start_line,
            'end_line': self.end_line,
            'children': [child.to_dict() for child in self.children]
        }


class CsParser:
    """C# 代码解析器类，使用 tree-sitter 解析 C# 语法树"""
    
    def __init__(self):
        if not HAS_TREE_SITTER:
            raise ImportError("tree-sitter 或 tree-sitter-c-sharp 未安装，请先安装: pip install tree-sitter tree-sitter-c-sharp")
        
        # 初始化日志
        self.logger = get_logger("cs_parser")
        
        # 初始化 C# 语言和解析器
        self.language = Language(tscsharp.language())
        self.parser = Parser(self.language)
        
        self.root: Optional[CsNode] = None  # 解析后的根节点
        self.source_file: Optional[str] = None  # 源文件路径
        self.source_id: Optional[str] = None  # 仓库相对 POSIX 路径唯一标识
        self.source_code: Optional[bytes] = None  # 源代码内容（字节格式）
        self.source_lines: List[str] = []  # 源代码行列表
        self.file_type: str = "else"  # 文件类型：page（有配对的 XAML 文件）或 else
    
    def parse_file(self, file_path: str) -> CsNode:
        """
        解析 C# 文件
        
        Args:
            file_path: C# 文件路径
            
        Returns:
            解析后的根节点
        """
        self.source_file = file_path
        
        # 判断文件类型
        self.file_type = self._determine_file_type(file_path)
        
        # 历史 WPF 仓库中仍存在 Windows-1252 源码。先严格按 UTF-8
        # 解码，仅在失败时使用可记录的兼容回退，避免静默丢字符。
        source_bytes = Path(file_path).read_bytes()
        try:
            content = source_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content = source_bytes.decode('cp1252')
                self.logger.warning(f"文件使用 Windows-1252 解码: {file_path}")
            except UnicodeDecodeError:
                content = source_bytes.decode('latin-1')
                self.logger.warning(f"文件使用 Latin-1 兼容解码: {file_path}")
        
        return self.parse_string(content)
    
    def parse_string(self, cs_content: str) -> CsNode:
        """
        解析 C# 代码字符串
        
        Args:
            cs_content: C# 代码字符串
            
        Returns:
            解析后的根节点
        """
        # 保存源代码
        self.source_code = cs_content.encode('utf-8')
        self.source_lines = cs_content.split('\n')
        
        # 使用 tree-sitter 解析
        tree = self.parser.parse(self.source_code)
        
        # 创建根节点
        self.root = CsNode(
            node_type='compilation_unit',
            name='root',
            start_line=1,
            end_line=len(self.source_lines)
        )
        
        # 递归解析语法树
        self._parse_node(tree.root_node, self.root)
        
        return self.root
    
    def _determine_file_type(self, cs_path: str) -> str:
        """
        判断 C# 文件类型
        
        检查是否存在对应的 XAML 文件
        - 如果 XAML 根标签是 Application，则为 root
        - 如果存在配对 XAML 文件，则为 page
        - 否则为 else
        
        Args:
            cs_path: C# 文件路径
            
        Returns:
            "root"、"page" 或 "else"
        """
        cs_path_obj = Path(cs_path)
        parent_dir = cs_path_obj.parent
        xaml_path = None
        
        # 处理 .xaml.cs 文件
        if cs_path.endswith('.xaml.cs'):
            # 映射示例：MainWindow.xaml.cs -> MainWindow.xaml
            base_name = cs_path_obj.name[:-8]  # 去掉 .xaml.cs
            xaml_path = parent_dir / f"{base_name}.xaml"
        
        # 处理 .cs 文件
        elif cs_path.endswith('.cs'):
            # 映射示例：MainWindow.cs -> MainWindow.xaml
            base_name = cs_path_obj.stem  # 获取不含扩展名的文件名
            xaml_path = parent_dir / f"{base_name}.xaml"
        
        # 在大小写敏感与不敏感文件系统上都保留仓库中的真实 XAML 拼写。
        if xaml_path:
            case_matches = [
                child
                for child in parent_dir.iterdir()
                if child.is_file()
                and child.name.casefold() == xaml_path.name.casefold()
            ]
            if len(case_matches) == 1:
                xaml_path = case_matches[0]

        # 如果找到配对的 XAML 文件，检查其根标签
        if xaml_path and xaml_path.exists():
            # 检查 XAML 文件的根标签是否为 Application
            if self._is_application_xaml(xaml_path):
                return "root"
            return "page"
        
        return "else"
    
    def _is_application_xaml(self, xaml_path: Path) -> bool:
        """
        检查 XAML 文件的根标签是否为 Application
        
        Args:
            xaml_path: XAML 文件路径
            
        Returns:
            True 如果根标签是 Application，否则 False
        """
        try:
            # 导入 XML 解析库
            try:
                import lxml.etree as ET
            except ImportError:
                import xml.etree.ElementTree as ET
            
            # 解析 XAML 文件
            tree = ET.parse(str(xaml_path))
            root = tree.getroot()
            
            # 提取标签名（去除命名空间）
            tag = root.tag
            if tag.startswith('{'):
                # 去除命名空间前缀，如 {http://...}Application -> Application
                tag = tag.split('}', 1)[1]
            
            return tag.endswith('Application')
        except Exception:
            # 解析失败时返回 False
            return False
    
    def _get_text(self, node: Node) -> str:
        """获取节点的文本内容"""
        if self.source_code is None:
            return ""
        return self.source_code[node.start_byte:node.end_byte].decode('utf-8')
    
    def _get_source_code(self, start_line: int, end_line: int) -> str:
        """获取指定行范围的源代码"""
        if not self.source_lines:
            return ""
        
        # 行号从1开始，列表索引从0开始
        lines = self.source_lines[start_line - 1:end_line]
        
        # 移除公共缩进
        return self._format_source_code('\n'.join(lines))
    
    def _format_source_code(self, source_code: str) -> str:
        """
        格式化源代码使其适合作为 LLM 输入
        
        处理策略：
        1. 移除公共缩进
        2. 去除多余的空白行
        3. 去除行尾空白
        
        Args:
            source_code: 原始源代码
            
        Returns:
            格式化后的源代码
        """
        if not source_code:
            return ""
        
        lines = source_code.split('\n')
        
        # 找到最小缩进（忽略空行）
        min_indent = float('inf')
        for line in lines:
            stripped = line.lstrip()
            if stripped:  # 非空行
                indent = len(line) - len(stripped)
                min_indent = min(min_indent, indent)
        
        if min_indent == float('inf'):
            min_indent = 0
        
        # 移除公共缩进并去除行尾空白
        formatted_lines = []
        for line in lines:
            if line.strip():  # 非空行
                formatted_lines.append(line[min_indent:].rstrip())
            else:
                formatted_lines.append('')
        
        # 去除开头和结尾的空行
        while formatted_lines and not formatted_lines[0]:
            formatted_lines.pop(0)
        while formatted_lines and not formatted_lines[-1]:
            formatted_lines.pop()
        
        return '\n'.join(formatted_lines)
    
    def _extract_modifiers(self, node: Node) -> List[str]:
        """提取修饰符（public, private, static 等）"""
        modifiers = []
        for child in node.children:
            if child.type in ['public', 'private', 'protected', 'internal', 
                            'static', 'virtual', 'override', 'abstract', 
                            'sealed', 'readonly', 'const', 'async', 'extern',
                            'partial', 'new', 'unsafe', 'volatile']:
                modifiers.append(child.type)
        return modifiers
    
    def _extract_attributes(self, node: Node) -> List[str]:
        """提取特性（Attribute）"""
        attributes = []
        for child in node.children:
            if child.type == 'attribute_list':
                attr_text = self._get_text(child)
                attributes.append(attr_text)
        return attributes
    
    def _extract_base_types(self, node: Node) -> List[str]:
        """提取基类和接口"""
        base_types = []
        for child in node.children:
            if child.type == 'base_list':
                # base_list 包含多个类型
                for subchild in child.children:
                    if subchild.type in ['identifier', 'qualified_name', 'generic_name']:
                        base_types.append(self._get_text(subchild))
        return base_types
    
    def _extract_parameters(self, node: Node) -> List[Dict[str, str]]:
        """提取参数列表"""
        parameters = []
        for child in node.children:
            if child.type == 'parameter_list':
                for param in child.children:
                    if param.type == 'parameter':
                        param_info = self._parse_parameter(param)
                        if param_info:
                            parameters.append(param_info)
        return parameters
    
    def _parse_parameter(self, node: Node) -> Optional[Dict[str, str]]:
        """解析单个参数"""
        param_type = None
        param_name = None
        param_modifier = None
        default_value = None
        
        for child in node.children:
            if child.type in ['predefined_type', 'identifier', 'qualified_name', 
                             'generic_name', 'array_type', 'nullable_type']:
                if param_type is None:  # 第一个类型节点是参数类型
                    param_type = self._get_text(child)
                else:  # 第二个标识符是参数名
                    param_name = self._get_text(child)
            elif child.type == 'identifier' and param_type is not None:
                param_name = self._get_text(child)
            elif child.type in ['ref', 'out', 'in', 'params']:
                param_modifier = child.type
            elif child.type == 'equals_value_clause':
                default_value = self._get_text(child)
        
        if param_name:
            result = {'name': param_name}
            if param_type:
                result['type'] = param_type
            if param_modifier:
                result['modifier'] = param_modifier
            if default_value:
                result['default'] = default_value
            return result
        
        return None
    
    def _find_child_by_type(self, node: Node, node_type: str) -> Optional[Node]:
        """查找指定类型的子节点"""
        for child in node.children:
            if child.type == node_type:
                return child
        return None
    
    def _parse_node(self, ts_node: Node, parent_cs_node: CsNode) -> None:
        """
        递归解析 tree-sitter 节点
        
        Args:
            ts_node: tree-sitter 节点
            parent_cs_node: 父 C# 节点
        """
        # 处理不同类型的节点
        for child in ts_node.children:
            cs_node = None
            
            # 命名空间
            if child.type == 'namespace_declaration':
                cs_node = self._parse_namespace(child)
            
            # 类
            elif child.type == 'class_declaration':
                cs_node = self._parse_class(child)
            
            # 接口
            elif child.type == 'interface_declaration':
                cs_node = self._parse_interface(child)
            
            # 结构体
            elif child.type == 'struct_declaration':
                cs_node = self._parse_struct(child)
            
            # 枚举
            elif child.type == 'enum_declaration':
                cs_node = self._parse_enum(child)
            
            # Using 声明
            elif child.type == 'using_directive':
                cs_node = self._parse_using(child)
            
            # 递归处理子节点
            if cs_node:
                parent_cs_node.children.append(cs_node)
            else:
                # 对于未特殊处理的节点，继续递归
                self._parse_node(child, parent_cs_node)
    
    def _parse_namespace(self, node: Node) -> CsNode:
        """解析命名空间"""
        name_node = self._find_child_by_type(node, 'qualified_name')
        if not name_node:
            name_node = self._find_child_by_type(node, 'identifier')
        
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        cs_node = CsNode(
            node_type='namespace',
            name=name,
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
        
        # 递归解析命名空间内的元素
        self._parse_node(node, cs_node)
        
        return cs_node
    
    def _parse_class(self, node: Node) -> CsNode:
        """解析类"""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        cs_node = CsNode(
            node_type='class',
            name=name,
            modifiers=self._extract_modifiers(node),
            base_types=self._extract_base_types(node),
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
        
        # 解析类成员
        body_node = self._find_child_by_type(node, 'declaration_list')
        if body_node:
            self._parse_class_members(body_node, cs_node)
        
        return cs_node
    
    def _parse_class_members(self, body_node: Node, parent_cs_node: CsNode) -> None:
        """解析类成员（方法、属性、字段等）"""
        for member in body_node.children:
            cs_node = None
            
            # 方法
            if member.type == 'method_declaration':
                cs_node = self._parse_method(member)
            
            # 构造函数
            elif member.type == 'constructor_declaration':
                cs_node = self._parse_constructor(member)
            
            # 属性
            elif member.type == 'property_declaration':
                cs_node = self._parse_property(member)
            
            # 字段
            elif member.type == 'field_declaration':
                cs_node = self._parse_field(member)
            
            # 事件
            elif member.type == 'event_declaration':
                cs_node = self._parse_event(member)
            
            # 嵌套类
            elif member.type == 'class_declaration':
                cs_node = self._parse_class(member)
            
            # 嵌套接口
            elif member.type == 'interface_declaration':
                cs_node = self._parse_interface(member)
            
            # 嵌套结构体
            elif member.type == 'struct_declaration':
                cs_node = self._parse_struct(member)
            
            # 嵌套枚举
            elif member.type == 'enum_declaration':
                cs_node = self._parse_enum(member)
            
            if cs_node:
                parent_cs_node.children.append(cs_node)
    
    def _parse_method(self, node: Node) -> CsNode:
        """解析方法"""
        # 提取返回类型
        return_type_node = self._find_child_by_type(node, 'predefined_type')
        if not return_type_node:
            return_type_node = self._find_child_by_type(node, 'identifier')
        if not return_type_node:
            return_type_node = self._find_child_by_type(node, 'generic_name')
        if not return_type_node:
            return_type_node = self._find_child_by_type(node, 'qualified_name')
        if not return_type_node:
            return_type_node = self._find_child_by_type(node, 'void_keyword')
        
        return_type = self._get_text(return_type_node) if return_type_node else 'void'
        
        # 提取方法名
        name = None
        for child in node.children:
            if child.type == 'identifier' and child != return_type_node:
                name = self._get_text(child)
                break
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return CsNode(
            node_type='method',
            name=name,
            modifiers=self._extract_modifiers(node),
            return_type=return_type,
            parameters=self._extract_parameters(node),
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
    
    def _parse_constructor(self, node: Node) -> CsNode:
        """解析构造函数"""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return CsNode(
            node_type='constructor',
            name=name,
            modifiers=self._extract_modifiers(node),
            parameters=self._extract_parameters(node),
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
    
    def _parse_property(self, node: Node) -> CsNode:
        """解析属性"""
        # 提取属性类型
        type_node = self._find_child_by_type(node, 'predefined_type')
        if not type_node:
            type_node = self._find_child_by_type(node, 'identifier')
        if not type_node:
            type_node = self._find_child_by_type(node, 'generic_name')
        if not type_node:
            type_node = self._find_child_by_type(node, 'qualified_name')
        
        data_type = self._get_text(type_node) if type_node else None
        
        # 提取属性名
        name = None
        for child in node.children:
            if child.type == 'identifier' and child != type_node:
                name = self._get_text(child)
                break
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return CsNode(
            node_type='property',
            name=name,
            modifiers=self._extract_modifiers(node),
            data_type=data_type,
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
    
    def _parse_field(self, node: Node) -> CsNode:
        """解析字段"""
        # 字段声明可能包含多个字段
        variable_declaration = self._find_child_by_type(node, 'variable_declaration')
        if not variable_declaration:
            return None
        
        # 提取字段类型
        type_node = self._find_child_by_type(variable_declaration, 'predefined_type')
        if not type_node:
            type_node = self._find_child_by_type(variable_declaration, 'identifier')
        if not type_node:
            type_node = self._find_child_by_type(variable_declaration, 'generic_name')
        if not type_node:
            type_node = self._find_child_by_type(variable_declaration, 'qualified_name')
        
        data_type = self._get_text(type_node) if type_node else None
        
        # 提取字段名（可能有多个）
        declarator = self._find_child_by_type(variable_declaration, 'variable_declarator')
        name = None
        if declarator:
            name_node = self._find_child_by_type(declarator, 'identifier')
            name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return CsNode(
            node_type='field',
            name=name,
            modifiers=self._extract_modifiers(node),
            data_type=data_type,
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
    
    def _parse_event(self, node: Node) -> CsNode:
        """解析事件"""
        # 提取事件类型
        type_node = self._find_child_by_type(node, 'predefined_type')
        if not type_node:
            type_node = self._find_child_by_type(node, 'identifier')
        if not type_node:
            type_node = self._find_child_by_type(node, 'generic_name')
        
        data_type = self._get_text(type_node) if type_node else None
        
        # 提取事件名
        name = None
        for child in node.children:
            if child.type == 'identifier' and child != type_node:
                name = self._get_text(child)
                break
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return CsNode(
            node_type='event',
            name=name,
            modifiers=self._extract_modifiers(node),
            data_type=data_type,
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
    
    def _parse_interface(self, node: Node) -> CsNode:
        """解析接口"""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        cs_node = CsNode(
            node_type='interface',
            name=name,
            modifiers=self._extract_modifiers(node),
            base_types=self._extract_base_types(node),
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
        
        # 解析接口成员
        body_node = self._find_child_by_type(node, 'declaration_list')
        if body_node:
            self._parse_class_members(body_node, cs_node)
        
        return cs_node
    
    def _parse_struct(self, node: Node) -> CsNode:
        """解析结构体"""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        cs_node = CsNode(
            node_type='struct',
            name=name,
            modifiers=self._extract_modifiers(node),
            base_types=self._extract_base_types(node),
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
        
        # 解析结构体成员
        body_node = self._find_child_by_type(node, 'declaration_list')
        if body_node:
            self._parse_class_members(body_node, cs_node)
        
        return cs_node
    
    def _parse_enum(self, node: Node) -> CsNode:
        """解析枚举"""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        cs_node = CsNode(
            node_type='enum',
            name=name,
            modifiers=self._extract_modifiers(node),
            base_types=self._extract_base_types(node),
            attributes=self._extract_attributes(node),
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
        
        # 解析枚举成员
        body_node = self._find_child_by_type(node, 'enum_member_declaration_list')
        if body_node:
            for member in body_node.children:
                if member.type == 'enum_member_declaration':
                    member_name_node = self._find_child_by_type(member, 'identifier')
                    member_name = self._get_text(member_name_node) if member_name_node else None
                    
                    member_start = member.start_point[0] + 1
                    member_end = member.end_point[0] + 1
                    
                    member_node = CsNode(
                        node_type='enum_member',
                        name=member_name,
                        start_line=member_start,
                        end_line=member_end,
                        source_code=self._get_source_code(member_start, member_end)
                    )
                    cs_node.children.append(member_node)
        
        return cs_node
    
    def _parse_using(self, node: Node) -> CsNode:
        """解析 using 声明"""
        # 提取 using 的命名空间或别名
        name_node = self._find_child_by_type(node, 'qualified_name')
        if not name_node:
            name_node = self._find_child_by_type(node, 'identifier')
        
        name = self._get_text(name_node) if name_node else None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return CsNode(
            node_type='using',
            name=name,
            start_line=start_line,
            end_line=end_line,
            source_code=self._get_source_code(start_line, end_line)
        )
    
    def get_elements_by_type(self, node_type: str, node: Optional[CsNode] = None) -> List[CsNode]:
        """
        根据节点类型查找所有匹配的元素
        
        Args:
            node_type: 要查找的节点类型（class, method, property 等）
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
        if node.node_type == node_type:
            results.append(node)
        
        # 递归检查子节点
        for child in node.children:
            results.extend(self.get_elements_by_type(node_type, child))
        
        return results
    
    def print_tree(self, node: Optional[CsNode] = None, indent: int = 0) -> None:
        """
        打印语法树结构（用于调试）
        
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
        modifiers_str = " ".join(node.modifiers) if node.modifiers else ""
        
        info_parts = [f"{node.node_type}"]
        if node.name:
            info_parts.append(f"'{node.name}'")
        if modifiers_str:
            info_parts.append(f"[{modifiers_str}]")
        if node.return_type:
            info_parts.append(f"-> {node.return_type}")
        if node.data_type:
            info_parts.append(f": {node.data_type}")
        
        info_str = " ".join(info_parts)
        self.logger.debug(f"{indent_str}{info_str} (L{node.start_line}-{node.end_line})")
        
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
    def parse_project(project_path: str, output_base_dir: str = "outputs") -> Dict[str, str]:
        """
        解析项目中所有 C# 文件并保存为 JSON 格式
        
        Args:
            project_path: 项目路径（例如 "repos/ExpenseItDemo"）
            output_base_dir: 输出基础目录（默认为 "outputs"）
            
        Returns:
            字典，键为 C# 文件路径，值为对应的 JSON 输出路径
        """
        project_path = Path(project_path)
        
        if not project_path.exists():
            raise FileNotFoundError(f"项目路径不存在: {project_path}")
        
        # 获取项目名称
        project_name = project_path.name
        
        # 创建输出目录：outputs/{project_name}/cs/
        output_dir = Path(output_base_dir) / project_name / "cs"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找所有 C# 文件（排除 Designer.cs 和 AssemblyInfo.cs）
        all_cs_files = discover_project_files(project_path, [".cs"])
        cs_files = [
            f for f in all_cs_files 
            if not f.name.endswith('.Designer.cs') 
            and not f.name == 'AssemblyInfo.cs'
        ]
        
        # 初始化日志
        logger = get_logger("cs_parser")
        
        if not cs_files:
            logger.warning(f"在 {project_path} 中未找到 C# 文件")
            return {}
        
        results = {}
        success_count = 0
        error_count = 0
        
        logger.info(f"开始解析项目: {project_name}")
        logger.info(f"找到 {len(cs_files)} 个 C# 文件（已排除 Designer 和 AssemblyInfo 文件）")
        logger.debug("-" * 70)
        
        for cs_file in cs_files:
            try:
                # 创建解析器实例
                parser = CsParser()
                
                # 解析 C# 文件
                parser.parse_file(str(cs_file))
                parser.source_id = repository_relative_id(cs_file, project_path)
                
                # 镜像仓库相对目录，避免同名文件互相覆盖。
                output_file = mirrored_json_path(output_dir, parser.source_id)
                
                # 保存为 JSON
                parser.save_to_json(str(output_file))
                
                results[str(cs_file)] = str(output_file)
                success_count += 1
                
                logger.info(f"✓ [C#     ] {cs_file.name} -> {output_file.relative_to(output_base_dir)}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"✗ {cs_file.name}: 解析失败 - {str(e)}")
        
        logger.debug("-" * 70)
        logger.info(f"解析完成: 成功 {success_count} 个, 失败 {error_count} 个")
        logger.info(f"输出目录: {output_dir}")
        
        return results


# 运行示例：python -m src.parser.cs_parser
if __name__ == "__main__":
    # 导入示例：from src.parser.cs_parser import CsParser
    
    # 方式1：解析单个 C# 文件
    # 示例：parser = CsParser()
    # 示例：parser.parse_file("repos/ExpenseItDemo/MainWindow.cs")
    # 示例：parser.print_tree()
    # 示例：parser.save_to_json("outputs/test/MainWindow.cs.json")
    
    # 方式2：批量解析整个项目
    results = CsParser.parse_project("repos/ExpenseItDemo")
