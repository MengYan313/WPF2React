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

import heapq
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

from src.common.logging import get_logger
from src.common.source_identity import (
    SourceIdentityError,
    artifact_source_id,
    component_name_from_page_id,
    control_json_path,
    normalize_source_id,
    page_id_from_cs_id,
)
from src.parser.io_utils import read_json, write_json


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
        self.dependency_evidence: Dict[str, List[Dict[str, Any]]] = {}
        self.ambiguous_references: Dict[str, List[Dict[str, Any]]] = {}
        self.migration_order: List[str] = []  # 迁移顺序（自底向上）
        self.cycle_groups: List[List[str]] = []
        self.candidate_edges: List[Dict[str, Any]] = []
        self.unsupported_references: List[Dict[str, Any]] = []
        
        # 初始化日志
        self.logger = get_logger("page_dependency")
    
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
        xaml_by_id: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
        xaml_by_casefold: Dict[str, List[str]] = {}
        for xaml_json_file in sorted(self.xaml_output_dir.rglob("*.xaml.json")):
            xaml_data = read_json(xaml_json_file)
            xaml_source_id = artifact_source_id(xaml_data, xaml_json_file)
            xaml_by_id[xaml_source_id] = (xaml_json_file, xaml_data)
            xaml_by_casefold.setdefault(xaml_source_id.casefold(), []).append(
                xaml_source_id
            )
        
        # 遍历所有 CS JSON 文件
        for cs_json_file in sorted(self.cs_output_dir.rglob("*.cs.json")):
            try:
                # 读取 JSON 文件
                cs_data = read_json(cs_json_file)
                
                # 检查 type 字段是否为 "page"
                if cs_data.get('type') != 'page':
                    continue
                
                # 获取源文件路径与唯一源码 ID。
                cs_source_file = cs_data.get('source_file')
                cs_source_id = artifact_source_id(cs_data, cs_json_file)
                if not cs_source_file:
                    continue

                expected_page_id = page_id_from_cs_id(normalize_source_id(cs_source_id))

                # 页面 ID 采用 XAML 仓库路径的真实大小写；仅在唯一时允许
                # code-behind 文件名的大小写差异匹配。
                matching_ids = (
                    [expected_page_id]
                    if expected_page_id in xaml_by_id
                    else xaml_by_casefold.get(expected_page_id.casefold(), [])
                )
                if len(matching_ids) != 1:
                    if matching_ids:
                        raise ValueError(
                            f"code-behind {cs_source_id} 对应多个大小写近似 XAML: "
                            f"{', '.join(sorted(matching_ids))}"
                        )
                    continue
                page_name = matching_ids[0]
                xaml_json_file, xaml_data = xaml_by_id[page_name]
                xaml_source_id = page_name
                
                xaml_source_file = xaml_data.get('source_file')
                if not xaml_source_file:
                    continue
                
                # 验证 XAML 文件的 type 也是 page（双重确认）
                if xaml_data.get('type') != 'page':
                    continue
                
                root_class = (
                    xaml_data.get('root', {}).get('attributes', {}).get('Class', '')
                )
                source_class_name = (
                    root_class.rsplit('.', 1)[-1]
                    if root_class
                    else Path(page_name).stem
                )
                valid_pages[page_name] = {
                    'page_id': page_name,
                    'source_class_name': source_class_name,
                    'source_class_full_name': root_class or source_class_name,
                    'source_namespace': root_class.rsplit('.', 1)[0]
                    if '.' in root_class
                    else '',
                    'component_name': component_name_from_page_id(page_name),
                    'xaml_source_id': xaml_source_id,
                    'cs_source_id': normalize_source_id(cs_source_id),
                    'xaml': xaml_source_file,
                    'cs': cs_source_file
                }
                
            except SourceIdentityError:
                raise
            except Exception as e:
                self.logger.warning(f"处理文件 {cs_json_file.name} 时出错: {e}")
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
        dependency_evidence: Dict[str, List[Dict[str, Any]]] = {}
        ambiguous_references: Dict[str, List[Dict[str, Any]]] = {}
        component_to_pages: Dict[str, Set[str]] = {}
        for page_id, files in self.valid_pages.items():
            component_to_pages.setdefault(files['source_class_name'], set()).add(page_id)
        
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
            
            # C# 引用使用组件符号，依赖图节点仍使用完整页面 ID。
            page_dependencies: Set[str] = set()
            page_evidence: List[Dict[str, Any]] = []

            def add_dependency(
                target_page_id: str,
                match: re.Match[str],
                resolution: str,
            ) -> None:
                page_dependencies.add(target_page_id)
                source_line = code_without_comments.count(
                    '\n', 0, match.start()
                ) + 1
                lines = code_without_comments.splitlines()
                page_evidence.append(
                    {
                        'source_page_id': current_page,
                        'target_page_id': target_page_id,
                        'source_symbol': component_name,
                        'source_line': source_line,
                        'confidence': 'high',
                        'resolution': resolution,
                        'evidence': lines[source_line - 1].strip()[:240],
                    }
                )

            for component_name, page_ids in component_to_pages.items():
                pattern = r'\bnew\s+' + re.escape(component_name) + r'\s*[({]'
                direct_match = re.search(pattern, code_without_comments)
                if not direct_match:
                    continue
                candidates = sorted(page_ids - {current_page})
                if len(candidates) == 1:
                    add_dependency(
                        candidates[0], direct_match, 'resolved_unique_symbol'
                    )
                    continue
                if not candidates:
                    continue

                qualified_matches = [
                    (page_id, match)
                    for page_id in candidates
                    if (
                        match := re.search(
                        r'\bnew\s+'
                        + re.escape(
                            self.valid_pages[page_id]['source_class_full_name']
                        )
                        + r'\s*[({]',
                        code_without_comments,
                        )
                    )
                ]
                if len(qualified_matches) == 1:
                    page_id, qualified_match = qualified_matches[0]
                    add_dependency(
                        page_id,
                        qualified_match,
                        'resolved_qualified_symbol',
                    )
                    continue

                current_namespace = files.get('source_namespace', '')
                same_namespace = [
                    page_id
                    for page_id in candidates
                    if self.valid_pages[page_id].get('source_namespace')
                    == current_namespace
                ]
                if len(same_namespace) == 1:
                    add_dependency(
                        same_namespace[0],
                        direct_match,
                        'resolved_same_namespace',
                    )
                    continue

                imported_namespaces = set(
                    re.findall(
                        r'^\s*using\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;',
                        code_without_comments,
                        flags=re.MULTILINE,
                    )
                )
                imported = [
                    page_id
                    for page_id in candidates
                    if self.valid_pages[page_id].get('source_namespace')
                    in imported_namespaces
                ]
                if len(imported) == 1:
                    add_dependency(
                        imported[0],
                        direct_match,
                        'resolved_imported_namespace',
                    )
                    continue

                ambiguous_references.setdefault(current_page, []).append(
                    {
                        'source_symbol': component_name,
                        'candidates': candidates,
                        'resolution': 'unresolved',
                        'source_line': code_without_comments.count(
                            '\n', 0, direct_match.start()
                        ) + 1,
                        'evidence': direct_match.group(0),
                    }
                )
                self.logger.warning(
                    "页面 %s 对 %s 的引用存在多个路径候选，未建立猜测性依赖边: %s",
                    current_page,
                    component_name,
                    ", ".join(candidates),
                )
            
            dependencies[current_page] = sorted(page_dependencies)
            dependency_evidence[current_page] = sorted(
                page_evidence,
                key=lambda item: (
                    item['target_page_id'],
                    item['source_line'],
                    item['source_symbol'],
                ),
            )
        
        self.dependencies = dependencies
        self.dependency_evidence = dependency_evidence
        self.ambiguous_references = ambiguous_references
        return dependencies

    @staticmethod
    def _walk_xaml_nodes(root: Dict[str, Any]) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        stack = [root] if root else []
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(
                reversed(
                    [
                        child
                        for child in node.get('children', [])
                        if isinstance(child, dict)
                    ]
                )
            )
        return nodes

    def _page_candidates_for_symbol(self, symbol: str) -> List[str]:
        """把框架符号映射为页面候选，不唯一时保持候选而不猜测。"""
        cleaned = symbol.strip().strip('"\'').rsplit('.', 1)[-1]
        variants = {cleaned}
        if cleaned.endswith('ViewModel'):
            variants.add(cleaned[:-5])
        if cleaned.endswith('Model'):
            variants.add(cleaned[:-5])
        return sorted(
            page_id
            for page_id, info in self.valid_pages.items()
            if info['source_class_name'] in variants
            or Path(page_id).stem in variants
        )

    def analyze_candidate_dependencies(self) -> List[Dict[str, Any]]:
        """保存 MVVM、框架导航、DI、字符串路由与反射候选及证据。"""
        if not self.valid_pages:
            self.find_valid_pages()
        candidates: List[Dict[str, Any]] = []
        unsupported: List[Dict[str, Any]] = []
        patterns = [
            (
                'prism-registration',
                re.compile(r'\bRegisterForNavigation\s*<\s*([A-Za-z_]\w*)'),
                'medium',
            ),
            (
                'prism-navigation',
                re.compile(r'\bRequestNavigate\s*\(\s*[^,\n]+,\s*["\']([^"\']+)["\']'),
                'medium',
            ),
            (
                'mvvmcross-navigation',
                re.compile(r'\b(?:ShowViewModel|Navigate)\s*<\s*([A-Za-z_]\w*)'),
                'medium',
            ),
            (
                'dependency-injection',
                re.compile(r'\b(?:GetRequiredService|GetService|Resolve)\s*<\s*([A-Za-z_]\w*(?:View|Window|Page))'),
                'medium',
            ),
            (
                'string-route',
                re.compile(r'\b(?:Navigate|RequestNavigate)\s*\(\s*["\']([^"\']+)["\']'),
                'low',
            ),
            (
                'reflection',
                re.compile(r'\b(?:Activator\.CreateInstance|Type\.GetType)\s*\('),
                'low',
            ),
        ]
        cs_to_page = {
            info['cs_source_id']: page_id
            for page_id, info in self.valid_pages.items()
        }
        for artifact in sorted(self.cs_output_dir.rglob('*.cs.json')):
            data = read_json(artifact)
            source_id = artifact_source_id(data, artifact)
            source_file = Path(str(data.get('source_file', '')))
            if not source_file.is_file():
                continue
            try:
                text = source_file.read_text(encoding='utf-8-sig')
            except UnicodeDecodeError:
                text = source_file.read_text(encoding='cp1252')
            for mechanism, pattern, confidence in patterns:
                for match in pattern.finditer(text):
                    symbol = match.group(1) if match.lastindex else ''
                    record = {
                        'source_id': source_id,
                        'source_page_id': cs_to_page.get(source_id),
                        'mechanism': mechanism,
                        'target_symbol': symbol or None,
                        'candidate_page_ids': (
                            self._page_candidates_for_symbol(symbol) if symbol else []
                        ),
                        'confidence': confidence,
                        'resolution': 'candidate' if symbol else 'unsupported',
                        'source_line': text.count('\n', 0, match.start()) + 1,
                        'evidence': match.group(0)[:240],
                    }
                    candidates.append(record)
                    if mechanism == 'reflection':
                        unsupported.append(record)
            if re.search(r'\b(?:ICommand|RelayCommand|DelegateCommand)\b', text) and re.search(
                r'\b(?:Navigate|ShowViewModel|RequestNavigate)\b', text
            ):
                match = re.search(r'\b(?:Navigate|ShowViewModel|RequestNavigate)\b', text)
                assert match is not None
                candidates.append(
                    {
                        'source_id': source_id,
                        'source_page_id': cs_to_page.get(source_id),
                        'mechanism': 'command-navigation',
                        'target_symbol': None,
                        'candidate_page_ids': [],
                        'confidence': 'low',
                        'resolution': 'candidate',
                        'source_line': text.count('\n', 0, match.start()) + 1,
                        'evidence': match.group(0),
                    }
                )

        for artifact in sorted(self.xaml_output_dir.rglob('*.xaml.json')):
            data = read_json(artifact)
            source_id = artifact_source_id(data, artifact)
            nodes = self._walk_xaml_nodes(data.get('root', {}))
            for node in nodes:
                attributes = node.get('attributes', {})
                if node.get('tag') == 'DataTemplate' and attributes.get('DataType'):
                    descendants = self._walk_xaml_nodes(node)[1:]
                    target = next(
                        (
                            str(item.get('tag'))
                            for item in descendants
                            if item.get('classification') == 'custom_control'
                        ),
                        None,
                    )
                    if target:
                        candidates.append(
                            {
                                'source_id': source_id,
                                'source_page_id': source_id
                                if source_id in self.valid_pages
                                else None,
                                'mechanism': 'mvvm-datatemplate-view-mapping',
                                'source_symbol': attributes['DataType'],
                                'target_symbol': target,
                                'candidate_page_ids': self._page_candidates_for_symbol(target),
                                'confidence': 'medium',
                                'resolution': 'candidate',
                                'source_line': node.get('source_line'),
                                'evidence': node.get('source_code', '')[:240],
                            }
                        )
                region_name = attributes.get('RegionName')
                if region_name:
                    candidates.append(
                        {
                            'source_id': source_id,
                            'source_page_id': source_id
                            if source_id in self.valid_pages
                            else None,
                            'mechanism': 'prism-region',
                            'target_symbol': region_name,
                            'candidate_page_ids': [],
                            'confidence': 'medium',
                            'resolution': 'candidate',
                            'source_line': node.get('source_line'),
                            'evidence': f'RegionName={region_name}',
                        }
                    )

        def key(item: Dict[str, Any]) -> Tuple[Any, ...]:
            return (
                item.get('source_id') or '',
                item.get('source_line') or 0,
                item.get('mechanism') or '',
                item.get('target_symbol') or '',
                tuple(item.get('candidate_page_ids', [])),
            )

        unique = {key(item): item for item in candidates}
        self.candidate_edges = [unique[item_key] for item_key in sorted(unique)]
        self.unsupported_references = sorted(unsupported, key=key)
        return self.candidate_edges
    
    def generate_migration_order(self) -> List[str]:
        """
        生成自底向上的迁移顺序（拓扑排序）
        
        使用 Kahn 算法进行拓扑排序：
        - 如果页面 A 依赖页面 B，则 B 必须在 A 之前迁移（自底向上）
        - 从没有前置依赖的页面开始，逐步处理依赖链
        
        Returns:
            迁移顺序列表（从无依赖的页面开始，到有最多依赖的页面结束）
        
        Raises:
            ValueError: 如果检测到循环依赖
        """
        if not self.dependencies:
            self.analyze_dependencies()
        
        pages = sorted(self.valid_pages)
        page_set = set(pages)
        index = 0
        indices: Dict[str, int] = {}
        low_links: Dict[str, int] = {}
        stack: List[str] = []
        on_stack: Set[str] = set()
        components: List[List[str]] = []

        def visit(page_id: str) -> None:
            nonlocal index
            indices[page_id] = index
            low_links[page_id] = index
            index += 1
            stack.append(page_id)
            on_stack.add(page_id)
            for dependency in sorted(self.dependencies.get(page_id, [])):
                if dependency not in page_set:
                    continue
                if dependency not in indices:
                    visit(dependency)
                    low_links[page_id] = min(
                        low_links[page_id], low_links[dependency]
                    )
                elif dependency in on_stack:
                    low_links[page_id] = min(
                        low_links[page_id], indices[dependency]
                    )
            if low_links[page_id] == indices[page_id]:
                component: List[str] = []
                while True:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == page_id:
                        break
                components.append(sorted(component))

        for page_id in pages:
            if page_id not in indices:
                visit(page_id)

        component_by_page = {
            page_id: component_index
            for component_index, component in enumerate(components)
            for page_id in component
        }
        self.cycle_groups = sorted(
            (component for component in components if len(component) > 1),
            key=lambda component: tuple(component),
        )
        graph: Dict[int, Set[int]] = {
            component_index: set() for component_index in range(len(components))
        }
        in_degree = {component_index: 0 for component_index in graph}
        for page_id, dependencies in self.dependencies.items():
            page_component = component_by_page[page_id]
            for dependency in dependencies:
                if dependency not in component_by_page:
                    continue
                dependency_component = component_by_page[dependency]
                if (
                    dependency_component != page_component
                    and page_component not in graph[dependency_component]
                ):
                    graph[dependency_component].add(page_component)
                    in_degree[page_component] += 1

        queue = [
            (tuple(components[component_index]), component_index)
            for component_index, degree in in_degree.items()
            if degree == 0
        ]
        heapq.heapify(queue)
        ordered_components: List[int] = []
        while queue:
            _, current = heapq.heappop(queue)
            ordered_components.append(current)
            for dependent in sorted(
                graph[current], key=lambda value: tuple(components[value])
            ):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    heapq.heappush(
                        queue, (tuple(components[dependent]), dependent)
                    )

        self.migration_order = [
            page_id
            for component_index in ordered_components
            for page_id in components[component_index]
        ]
        return self.migration_order
    
    def generate_dependency_graph(self) -> Dict[str, Any]:
        """
        生成依赖关系图的完整数据结构
        
        Returns:
            包含项目信息、页面列表、依赖关系和迁移顺序的字典
        """
        if not self.dependencies:
            self.analyze_dependencies()
        
        # 生成迁移顺序（如果还没有生成）
        if not self.migration_order:
            self.generate_migration_order()
        
        # 构建页面详细信息
        pages_info = {}
        for page_name, files in self.valid_pages.items():
            project_output_dir = self.output_base_dir / self.project_name
            pages_info[page_name] = {
                'page_id': page_name,
                'component_name': files['component_name'],
                'source_class_name': files['source_class_name'],
                'source_class_full_name': files['source_class_full_name'],
                'source_namespace': files['source_namespace'],
                'ambiguous_references': self.ambiguous_references.get(page_name, []),
                'xaml_source_id': files['xaml_source_id'],
                'cs_source_id': files['cs_source_id'],
                'xaml_file': files['xaml'],
                'cs_file': files['cs'],
                'control_file': control_json_path(
                    project_output_dir / 'dependency', page_name
                ).relative_to(project_output_dir).as_posix(),
                'dependencies': self.dependencies.get(page_name, []),
                'dependency_evidence': self.dependency_evidence.get(page_name, []),
                'dependency_count': len(self.dependencies.get(page_name, []))
            }
        
        # 计算被依赖次数
        depended_by_count = {page: 0 for page in self.valid_pages.keys()}
        for deps in self.dependencies.values():
            for dep in deps:
                depended_by_count[dep] += 1
        
        # 添加被依赖信息和迁移顺序索引
        for idx, page_name in enumerate(self.migration_order):
            pages_info[page_name]['depended_by_count'] = depended_by_count[page_name]
            pages_info[page_name]['migration_order'] = idx + 1  # 从1开始编号
        
        # 统计孤立页面和依赖链中的页面（与 cs_dependency.json 格式统一）
        # 孤立页面：既没有依赖其他页面，也没有被其他页面依赖
        isolated_pages_count = 0
        pages_in_dependency_chain_count = 0
        
        for page_name in self.valid_pages.keys():
            deps = self.dependencies.get(page_name, [])
            depended_by = depended_by_count.get(page_name, 0)
            
            if not deps and depended_by == 0:
                isolated_pages_count += 1
            else:
                pages_in_dependency_chain_count += 1
        
        # 构建完整的依赖图
        dependency_graph = {
            'project_name': self.project_name,
            'total_pages': len(self.valid_pages),
            'pages': pages_info,
            'migration_order': self.migration_order,  # 迁移顺序列表
            'cycle_groups': self.cycle_groups,
            'dependency_evidence': self.dependency_evidence,
            'ambiguous_references': self.ambiguous_references,
            'candidate_edges': self.candidate_edges,
            'unsupported_references': self.unsupported_references,
            'dependency_summary': {
                'total_dependencies': sum(len(deps) for deps in self.dependencies.values()),
                'dependency_evidence_count': sum(
                    len(items) for items in self.dependency_evidence.values()
                ),
                'isolated_pages': isolated_pages_count,
                'pages_in_dependency_chain': pages_in_dependency_chain_count,
                'cycle_group_count': len(self.cycle_groups),
                'candidate_edge_count': len(self.candidate_edges),
                'unsupported_reference_count': len(
                    self.unsupported_references
                ),
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
        
        # 输出文件路径：outputs/{project_name}/dependency/page_dependency.json
        output_file = self.output_base_dir / self.project_name / "dependency" / "page_dependency.json"
        write_json(output_file, dependency_graph)
        
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
        
        # 初始化日志
        logger = get_logger("page_dependency")
        
        # 查找有效页面
        valid_pages = analyzer.find_valid_pages()
        logger.info(f"项目: {analyzer.project_name}")
        logger.info(f"找到 {len(valid_pages)} 个有效页面（type=page）")
        
        # 分析依赖关系
        dependencies = analyzer.analyze_dependencies()
        analyzer.analyze_candidate_dependencies()
        
        # 生成迁移顺序
        try:
            migration_order = analyzer.generate_migration_order()
            logger.info(f"生成迁移顺序: {' -> '.join(migration_order)}")
        except ValueError as e:
            logger.error(f"❌ 错误: {e}")
            raise
        
        # 保存结果
        output_file = analyzer.save_to_json()
        
        return analyzer.generate_dependency_graph(), output_file
    
    def print_summary(self):
        """打印依赖关系摘要"""
        if not self.dependencies:
            self.analyze_dependencies()
        
        # 生成迁移顺序
        if not self.migration_order:
            try:
                self.generate_migration_order()
            except ValueError as e:
                self.logger.error(f"❌ 错误: {e}")
                return
        
        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"项目: {self.project_name}")
        self.logger.info("=" * 70)
        self.logger.info(f"\n有效页面数: {len(self.valid_pages)}")
        self.logger.info("\n页面列表:")
        for page_name, files in sorted(self.valid_pages.items()):
            self.logger.info(f"  - {page_name}")
            self.logger.info(f"    XAML: {files['xaml']}")
            self.logger.info(f"    CS:   {files['cs']}")
        
        self.logger.info("\n" + "-" * 70)
        self.logger.info("依赖关系:")
        self.logger.info("-" * 70)
        
        for page, deps in sorted(self.dependencies.items()):
            if deps:
                self.logger.info(f"\n  {page} →")
                for dep in deps:
                    self.logger.info(f"    - {dep}")
            else:
                self.logger.info(f"\n  {page} (无依赖)")
        
        self.logger.info("\n" + "-" * 70)
        self.logger.info("迁移顺序（自底向上）:")
        self.logger.info("-" * 70)
        for idx, page in enumerate(self.migration_order, 1):
            self.logger.info(f"  {idx}. {page}")
        
        self.logger.info("\n" + "=" * 70)


# 运行示例：python -m src.parser.page_dependency
if __name__ == "__main__":
    # 导入示例：from src.parser.page_dependency import PageDependencyAnalyzer

    # 初始化日志
    logger = get_logger("page_dependency")

    # 方式1：使用静态方法（推荐）
    graph, output_file = PageDependencyAnalyzer.analyze_project("ExpenseItDemo")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ 页面依赖分析完成")
    logger.info("=" * 70)
    logger.info(f"\n输出文件: {output_file}")
    logger.info(f"\n总页面数: {graph['total_pages']}")
    logger.info(f"总依赖数: {graph['dependency_summary']['total_dependencies']}")
    logger.info(f"孤立页面: {graph['dependency_summary']['isolated_pages']}")
    logger.info(f"依赖链中的页面: {graph['dependency_summary']['pages_in_dependency_chain']}")
    logger.info(f"\n迁移顺序: {' -> '.join(graph['migration_order'])}")
    logger.info("\n" + "=" * 70)

    # 方式2：使用实例方法
    # 示例：analyzer = PageDependencyAnalyzer("ExpenseItDemo")
    # 示例：valid_pages = analyzer.find_valid_pages()
    # 示例：dependencies = analyzer.analyze_dependencies()
    # 示例：output_file = analyzer.save_to_json()
