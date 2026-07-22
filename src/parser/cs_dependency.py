"""
C# 文件依赖关系识别模块
用于分析 WPF 项目中 C# 文件之间的依赖关系

本模块通过读取 C# 解析器的输出 (JSON 文件)，
分析 C# 文件之间的类、函数等元素的依赖关系。

工作流程:
1. 读取 outputs/{project_name}/cs/*.json 文件
2. 跳过 type 为 "root" 或 "page" 的文件
3. 提取每个文件中定义的类名
4. 分析源代码中对其他类的引用
5. 构建依赖图并生成迁移顺序
6. 保存为 JSON 文件
"""

import json
import heapq
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict

from src.common.logging import get_logger
from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    SourceIdentityError,
    artifact_source_id,
)
from src.parser.io_utils import read_json, write_json


class CsDependencyAnalyzer:
    """C# 文件依赖关系分析器"""
    
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
        
        # 初始化日志
        self.logger = get_logger("cs_dependency")
        
        # 存储文件信息
        self.cs_files: Dict[str, Dict[str, Any]] = {}  # {文件名: 文件信息}
        self.type_definitions: Dict[str, Set[str]] = {}  # {文件名: {类型名集合（类、接口、枚举、结构体）}}
        self.dependencies: Dict[str, List[str]] = {}  # {文件名: [依赖的文件列表]}
        self.migration_order: List[str] = []  # 迁移顺序（自底向上）
        self.cycle_groups: List[List[str]] = []  # 强连通分量中的循环依赖组
        self._source_patterns_key: Tuple[str, ...] = ()
        self._source_patterns: List[re.Pattern[str]] = []
    
    def load_cs_files(self) -> Dict[str, Dict[str, Any]]:
        """
        加载所有 C# JSON 文件
        
        Returns:
            文件信息字典 {文件名: 文件数据}
        """
        if not self.cs_output_dir.exists():
            raise FileNotFoundError(
                f"C# 输出目录不存在: {self.cs_output_dir}\n"
                f"请先运行 C# 解析器: python -m src.parser.cs_parser"
            )
        
        cs_files = {}
        
        for json_file in sorted(self.cs_output_dir.rglob("*.json")):
            try:
                data = read_json(json_file)
                
                file_type = data.get("type", "")
                source_file = data.get("source_file", "")
                
                # 跳过 type 为 "root" 或 "page" 的文件
                if file_type in ("root", "page"):
                    continue
                
                file_name = artifact_source_id(data, json_file)
                
                cs_files[file_name] = {
                    "source_file": source_file,
                    "type": file_type,
                    "data": data
                }
                
            except SourceIdentityError:
                raise
            except Exception as e:
                self.logger.warning(f"无法读取文件 {json_file}: {e}")
                continue
        
        self.cs_files = cs_files
        return cs_files
    
    def extract_type_definitions(self, file_name: str, node: Dict[str, Any]) -> Set[str]:
        """
        递归提取节点中定义的所有类型（类、接口、枚举、结构体）
        
        Args:
            file_name: 文件名
            node: 节点数据
            
        Returns:
            类型名集合
        """
        type_names = set()
        
        node_type = node.get("node_type", "")
        
        # 提取类、接口、枚举、结构体
        if node_type in ("class", "interface", "enum", "struct"):
            type_name = node.get("name")
            if type_name:
                type_names.add(type_name)
        
        # 递归处理子节点
        children = node.get("children", [])
        for child in children:
            type_names.update(self.extract_type_definitions(file_name, child))
        
        return type_names
    
    def extract_all_type_definitions(self) -> Dict[str, Set[str]]:
        """
        提取所有文件中定义的类型（类、接口、枚举、结构体）
        
        Returns:
            {文件名: {类型名集合}}
        """
        type_definitions = {}
        
        for file_name, file_info in self.cs_files.items():
            data = file_info["data"]
            root = data.get("root", {})
            
            # 提取所有类型定义
            types = self.extract_type_definitions(file_name, root)
            type_definitions[file_name] = types
        
        self.type_definitions = type_definitions
        return type_definitions
    
    def extract_types_from_string(self, type_string: str, all_type_names: Set[str]) -> Set[str]:
        """
        从类型字符串中提取所有可能的类型引用（包括泛型参数）
        
        例如：
        - "ObservableCollection<LineItem>" -> {"LineItem"}
        - "List<ExpenseReport, LineItem>" -> {"ExpenseReport", "LineItem"}
        - "System.Collections.Generic.List<LineItem>" -> {"LineItem"}
        
        Args:
            type_string: 类型字符串
            all_type_names: 所有可能的类型名集合
            
        Returns:
            引用的类型名集合
        """
        referenced_types = set()
        
        if not type_string:
            return referenced_types
        
        # 提取泛型参数中的类型（如 <LineItem>, <ExpenseReport, LineItem>）
        generic_match = re.search(r'<([^>]+)>', type_string)
        if generic_match:
            generic_params = generic_match.group(1)
            # 分割泛型参数（处理嵌套泛型）
            # 简单处理：按逗号分割，但需要处理嵌套的 <>
            params = []
            depth = 0
            current_param = ""
            for char in generic_params:
                if char == '<':
                    depth += 1
                    current_param += char
                elif char == '>':
                    depth -= 1
                    current_param += char
                elif char == ',' and depth == 0:
                    params.append(current_param.strip())
                    current_param = ""
                else:
                    current_param += char
            if current_param:
                params.append(current_param.strip())
            
            # 从每个泛型参数中提取类型名
            for param in params:
                # 移除命名空间前缀
                type_name = param.split('.')[-1].split('<')[0].split('[')[0].strip()
                if type_name in all_type_names:
                    referenced_types.add(type_name)
        
        # 提取主类型名（泛型类型本身，如 ObservableCollection）
        main_type = type_string.split('<')[0].split('[')[0].split('.')[-1].strip()
        if main_type in all_type_names:
            referenced_types.add(main_type)
        
        return referenced_types
    
    def extract_type_references_from_node(self, node: Dict[str, Any], all_type_names: Set[str]) -> Set[str]:
        """
        从节点中提取类型引用（包括基类、字段类型、返回类型、参数类型等）
        
        Args:
            node: 节点数据
            all_type_names: 所有可能的类型名集合
            
        Returns:
            引用的类型名集合
        """
        referenced_types = set()
        
        # 1. 提取基类和接口（base_types），包括泛型参数
        base_types = node.get("base_types", [])
        for base_type in base_types:
            referenced_types.update(self.extract_types_from_string(base_type, all_type_names))
        
        # 2. 提取字段类型（data_type）
        data_type = node.get("data_type")
        if data_type:
            referenced_types.update(self.extract_types_from_string(data_type, all_type_names))
        
        # 3. 提取返回类型（return_type）
        return_type = node.get("return_type")
        if return_type:
            referenced_types.update(self.extract_types_from_string(return_type, all_type_names))
        
        # 4. 提取参数类型
        parameters = node.get("parameters", [])
        for param in parameters:
            if isinstance(param, dict):
                param_type = param.get("type") or param.get("data_type")
                if param_type:
                    referenced_types.update(self.extract_types_from_string(param_type, all_type_names))
        
        # 5. 从源代码中提取类型引用（如 new TypeName(), TypeName.Method() 等）
        source_code = node.get("source_code", "")
        if source_code:
            referenced_types.update(self.find_type_references_in_source(source_code, all_type_names))
        
        # 递归处理子节点
        children = node.get("children", [])
        for child in children:
            referenced_types.update(self.extract_type_references_from_node(child, all_type_names))
        
        return referenced_types
    
    def find_type_references_in_source(self, source_code: str, all_type_names: Set[str]) -> Set[str]:
        """
        在源代码中查找类型引用
        
        匹配模式：
        - new TypeName()
        - TypeName.Method()
        - TypeName.Property
        - TypeName variable
        - : TypeName (继承/实现)
        - TypeName[] (数组)
        - List<TypeName> (泛型)
        
        Args:
            source_code: 源代码字符串
            all_type_names: 所有可能的类型名集合
            
        Returns:
            引用的类型名集合
        """
        if not source_code:
            return set()
        
        pattern_key = tuple(sorted(all_type_names, key=lambda name: (-len(name), name)))
        if not pattern_key:
            return set()

        # 旧实现对每个语法树节点逐类型编译并扫描 7 个正则，
        # 复杂项目会退化为 O(源码长度 × 类型数)。将类型名合并为一个
        # 备选组并按类型集合缓存，保留原有 7 种语义模式。
        if pattern_key != self._source_patterns_key:
            alternatives = "|".join(re.escape(name) for name in pattern_key)
            type_group = rf"({alternatives})"
            self._source_patterns = [
                re.compile(rf'\bnew\s+{type_group}\s*[\[\(]'),
                re.compile(rf'\b{type_group}\s*\.'),
                re.compile(rf':\s*{type_group}\b'),
                re.compile(rf'\b{type_group}\s+\w+'),
                re.compile(rf'<\s*{type_group}\s*>'),
                re.compile(rf'<\s*{type_group}\s*,'),
                re.compile(rf',\s*{type_group}\s*>'),
            ]
            self._source_patterns_key = pattern_key

        return {
            match.group(1)
            for pattern in self._source_patterns
            for match in pattern.finditer(source_code)
        }
    
    def analyze_dependencies(self) -> Dict[str, List[str]]:
        """
        分析文件之间的依赖关系
        
        依赖检测包括：
        1. 基类和接口（base_types）
        2. 字段类型（data_type）
        3. 返回类型（return_type）
        4. 参数类型（parameters）
        5. 源代码中的类型引用（如 new TypeName(), TypeName.Method() 等）
        
        Returns:
            {文件名: [依赖的文件列表]}
        """
        # 首先提取所有类型定义（类、接口、枚举、结构体）
        self.extract_all_type_definitions()
        
        # 构建类型名到文件名的映射
        type_to_files: Dict[str, Set[str]] = defaultdict(set)
        all_type_names = set()
        
        for file_name, types in self.type_definitions.items():
            for type_name in types:
                type_to_files[type_name].add(file_name)
                all_type_names.add(type_name)
        
        dependencies: Dict[str, List[str]] = defaultdict(list)
        
        # 分析每个文件的依赖
        for file_name, file_info in self.cs_files.items():
            data = file_info["data"]
            root = data.get("root", {})
            
            # 从整个语法树中提取类型引用（包括基类、字段类型、返回类型、源代码引用等）
            referenced_types = self.extract_type_references_from_node(root, all_type_names)
            
            # 移除自身定义的类型（避免自引用）
            self_types = self.type_definitions.get(file_name, set())
            referenced_types -= self_types
            
            # 将类型名转换为文件名
            for type_name in referenced_types:
                for dep_file in sorted(type_to_files.get(type_name, set())):
                    if dep_file != file_name and dep_file not in dependencies[file_name]:
                        dependencies[file_name].append(dep_file)
        
        # 转换为普通字典并排序
        self.dependencies = {
            file_name: sorted(deps) 
            for file_name, deps in dependencies.items()
        }
        
        return self.dependencies
    
    def _strongly_connected_components(self, files: List[str]) -> List[List[str]]:
        """使用 Tarjan 算法生成确定性强连通分量。"""
        file_set = set(files)
        index = 0
        indices: Dict[str, int] = {}
        low_links: Dict[str, int] = {}
        stack: List[str] = []
        on_stack: Set[str] = set()
        components: List[List[str]] = []

        def visit(file_name: str) -> None:
            nonlocal index
            indices[file_name] = index
            low_links[file_name] = index
            index += 1
            stack.append(file_name)
            on_stack.add(file_name)

            for dependency in sorted(self.dependencies.get(file_name, [])):
                if dependency not in file_set:
                    continue
                if dependency not in indices:
                    visit(dependency)
                    low_links[file_name] = min(
                        low_links[file_name], low_links[dependency]
                    )
                elif dependency in on_stack:
                    low_links[file_name] = min(
                        low_links[file_name], indices[dependency]
                    )

            if low_links[file_name] == indices[file_name]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == file_name:
                        break
                components.append(sorted(component))

        for file_name in sorted(files):
            if file_name not in indices:
                visit(file_name)

        return components

    def generate_migration_order(self) -> List[str]:
        """
        生成迁移顺序（拓扑排序，自底向上）
        
        优化策略：
        1. 先迁移所有真正的孤立文件（既没有依赖其他文件，也没有被其他文件依赖）
        2. 再自底向上迁移依赖链中的文件（使用拓扑排序）
        
        孤立文件定义：
        - 没有依赖其他文件（dependency_count == 0）
        - 没有被其他文件依赖（depended_by_count == 0）
        
        使用强连通分量压缩图和 Kahn 算法进行拓扑排序：
        - 如果文件 A 依赖文件 B，则 B 必须在 A 之前迁移（自底向上）
        - 循环依赖组作为一个拓扑节点，组内按名称确定性排序
        
        Returns:
            迁移顺序列表（先孤立文件，再依赖链中的文件）
            
        """
        # 计算每个文件被依赖的次数
        depended_by_count: Dict[str, int] = {file_name: 0 for file_name in self.cs_files.keys()}
        for file_name, deps in self.dependencies.items():
            for dep in deps:
                if dep in depended_by_count:
                    depended_by_count[dep] += 1
        
        # 分离真正的孤立文件（既没有依赖，也没有被依赖）和依赖链中的文件
        isolated_files = []
        files_in_dependency_chain = []
        
        for file_name in self.cs_files.keys():
            deps = self.dependencies.get(file_name, [])
            depended_by = depended_by_count.get(file_name, 0)
            
            # 孤立文件：既没有依赖其他文件，也没有被其他文件依赖
            if not deps and depended_by == 0:
                isolated_files.append(file_name)
            else:
                files_in_dependency_chain.append(file_name)
        
        # 孤立文件按字母顺序排序（保证可重复性）
        isolated_files.sort()
        
        components = self._strongly_connected_components(files_in_dependency_chain)
        component_by_file = {
            file_name: component_index
            for component_index, component in enumerate(components)
            for file_name in component
        }
        self.cycle_groups = sorted(
            (component for component in components if len(component) > 1),
            key=lambda component: tuple(component),
        )

        graph: Dict[int, Set[int]] = {
            component_index: set() for component_index in range(len(components))
        }
        in_degree: Dict[int, int] = {
            component_index: 0 for component_index in range(len(components))
        }
        for file_name, dependencies in self.dependencies.items():
            if file_name not in component_by_file:
                continue
            file_component = component_by_file[file_name]
            for dependency in dependencies:
                if dependency not in component_by_file:
                    continue
                dependency_component = component_by_file[dependency]
                if (
                    dependency_component != file_component
                    and file_component not in graph[dependency_component]
                ):
                    graph[dependency_component].add(file_component)
                    in_degree[file_component] += 1

        queue = [
            (tuple(components[component_index]), component_index)
            for component_index, degree in in_degree.items()
            if degree == 0
        ]
        heapq.heapify(queue)
        ordered_components = []
        while queue:
            _, current = heapq.heappop(queue)
            ordered_components.append(current)
            for dependent in sorted(
                graph[current], key=lambda index: tuple(components[index])
            ):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    heapq.heappush(
                        queue, (tuple(components[dependent]), dependent)
                    )

        dependency_chain_order = [
            file_name
            for component_index in ordered_components
            for file_name in components[component_index]
        ]
        
        # 合并迁移顺序：先孤立文件，再依赖链中的文件
        migration_order = isolated_files + dependency_chain_order
        
        self.migration_order = migration_order
        return migration_order
    
    def generate_dependency_graph(self) -> Dict[str, Any]:
        """
        生成完整的依赖关系图
        
        Returns:
            依赖关系图字典
        """
        # 确保已分析依赖
        if not self.dependencies:
            self.analyze_dependencies()
        
        # 确保已生成迁移顺序
        if not self.migration_order:
            self.generate_migration_order()
        
        # 构建文件信息（格式与 page_dependency.json 保持一致）
        files_info = {}
        migration_indices = {
            file_name: index for index, file_name in enumerate(self.migration_order)
        }
        for file_name, file_info in self.cs_files.items():
            deps = self.dependencies.get(file_name, [])
            migration_idx = migration_indices.get(file_name, -1)
            
            files_info[file_name] = {
                "cs_file": file_info["source_file"],  # 与 page_dependency.json 中的 "cs_file" 字段保持一致
                "type": file_info["type"],
                "dependencies": deps,
                "dependency_count": len(deps),
                "depended_by_count": sum(1 for deps_list in self.dependencies.values() if file_name in deps_list),
                "migration_order": migration_idx + 1 if migration_idx >= 0 else None,
                # sorted() 保证可重复输出：set 的迭代顺序随 Python 进程的字符串
                # 哈希随机化而变，不排序会导致 cs_dependency.json 每次运行都不同。
                "defined_types": sorted(self.type_definitions.get(file_name, set()))  # 定义的类型（类、接口、枚举、结构体）
            }
        
        # 构建完整的依赖图（格式与 page_dependency.json 保持一致）
        # 统计孤立文件（既没有依赖其他文件，也没有被其他文件依赖）和依赖链中的文件
        isolated_files_count = 0
        files_in_dependency_chain_count = 0
        
        for file_name in self.cs_files.keys():
            deps = self.dependencies.get(file_name, [])
            depended_by = sum(1 for deps_list in self.dependencies.values() if file_name in deps_list)
            
            if not deps and depended_by == 0:
                isolated_files_count += 1
            else:
                files_in_dependency_chain_count += 1
        
        dependency_graph = {
            "id_scheme": SOURCE_ID_SCHEME,
            "project_name": self.project_name,
            "total_files": len(self.cs_files),
            "files": files_info,
            "migration_order": self.migration_order,
            "cycle_groups": self.cycle_groups,
            "dependency_summary": {
                "total_dependencies": sum(len(deps) for deps in self.dependencies.values()),
                "isolated_files": isolated_files_count,
                "files_in_dependency_chain": files_in_dependency_chain_count,
                "cycle_group_count": len(self.cycle_groups),
                "files_in_cycles": sum(len(group) for group in self.cycle_groups),
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
        
        # 输出文件路径：outputs/{project_name}/dependency/cs_dependency.json
        output_file = self.output_base_dir / self.project_name / "dependency" / "cs_dependency.json"
        write_json(output_file, dependency_graph)
        
        return str(output_file)
    
    @staticmethod
    def analyze_project(project_name: str, output_dir: str = "outputs") -> Tuple[Dict[str, Any], str]:
        """
        分析项目的 C# 文件依赖关系（静态方法，便于直接调用）
        
        Args:
            project_name: 项目名称
            output_dir: 输出目录
            
        Returns:
            (依赖关系图字典, 输出文件路径)
        """
        analyzer = CsDependencyAnalyzer(project_name, output_dir)
        
        # 加载文件
        analyzer.load_cs_files()
        
        # 分析依赖
        analyzer.analyze_dependencies()
        
        # 生成迁移顺序
        analyzer.generate_migration_order()
        
        # 保存结果
        output_file = analyzer.save_to_json()
        
        return analyzer.generate_dependency_graph(), output_file


# 运行示例：python -m src.parser.cs_dependency
if __name__ == "__main__":
    import sys
    
    # 方式1：使用静态方法（推荐）
    project_name = "ExpenseItDemo"
    if len(sys.argv) > 1:
        project_name = sys.argv[1]
    
    logger = get_logger("cs_dependency")
    
    try:
        graph, output_file = CsDependencyAnalyzer.analyze_project(project_name)
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ C# 文件依赖分析完成")
        logger.info("=" * 70)
        logger.info(f"\n输出文件: {output_file}")
        logger.info(f"\n总文件数: {graph['total_files']}")
        logger.info(f"总依赖数: {graph['dependency_summary']['total_dependencies']}")
        logger.info(f"孤立文件: {graph['dependency_summary']['isolated_files']}")
        logger.info(f"依赖链中的文件: {graph['dependency_summary']['files_in_dependency_chain']}")
        logger.info(f"\n迁移顺序: {' -> '.join(graph['migration_order'])}")
        
        logger.info("\n" + "-" * 70)
        logger.info("文件依赖详情:")
        logger.info("-" * 70)
        for idx, file_name in enumerate(graph['migration_order'], 1):
            file_info = graph['files'][file_name]
            deps = file_info['dependencies']
            deps_str = ', '.join(deps) if deps else '无'
            defined_types = file_info.get('defined_types', [])
            types_str = ', '.join(defined_types) if defined_types else '无'
            logger.info(f"\n  {idx}. {file_name}")
            logger.info(f"     定义的类型: {types_str}")
            logger.info(f"     依赖的文件: {deps_str}")
            logger.info(f"     被依赖次数: {file_info['depended_by_count']}")
        
        logger.info("\n" + "=" * 70)
        
    except Exception as e:
        logger = get_logger("cs_dependency")
        logger.error(f"\n✗ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 方式2：使用实例方法
    # 示例：analyzer = CsDependencyAnalyzer("ExpenseItDemo")
    # 示例：cs_files = analyzer.load_cs_files()
    # 示例：dependencies = analyzer.analyze_dependencies()
    # 示例：migration_order = analyzer.generate_migration_order()
    # 示例：output_file = analyzer.save_to_json()
