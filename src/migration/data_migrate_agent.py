"""
Data Migration Agent

负责迁移项目数据资源，将 WPF XAML 数据资源转换为 TypeScript 格式供 React 使用。
"""

import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig, build_json_system_prompt
from .base import BaseMigrationAgent
from .messages import DataMigrationRequest, DataMigrationResponse


class DataMigrateAgent(BaseMigrationAgent):
    """
    数据迁移 Agent
    
    职责：
    1. 读取 data_resources.json 文件
    2. 遍历每个数据资源，将 source_code 迁移为 TypeScript
    3. 处理依赖的 class_info 和嵌套的 dependency_classes
    4. 将所有迁移结果统一存放在 results/{project_name}/data.ts 中
    """
    
    def __init__(
        self,
        project_name: str = "",
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化数据迁移 Agent
        
        Args:
            project_name: 项目名称（可选，可通过消息传递）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（用于数据迁移）
        """
        # 如果没有提供 LLM 配置，使用默认配置
        if llm_config is None:
            llm_config = LLMConfig.json_mode_config()
        
        super().__init__(
            agent_type="DataMigrateAgent",
            llm_config=llm_config,
            output_base_dir=output_base_dir
        )
        
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
    
    def _collect_all_dependency_class_names(self, class_info: Dict[str, Any]) -> List[str]:
        """
        收集所有依赖类的名称（包括嵌套依赖）
        
        Args:
            class_info: 类信息字典，包含 class_name 和 dependency_classes
        
        Returns:
            所有依赖类名称的列表（包括当前类）
        """
        if not class_info:
            return []
        
        class_names = []
        
        # 添加当前类名
        class_name = class_info.get('class_name')
        if class_name:
            class_names.append(class_name)
        
        # 递归收集依赖类的名称
        dependency_classes = class_info.get("dependency_classes", [])
        for dep_class in dependency_classes:
            dep_names = self._collect_all_dependency_class_names(dep_class)
            class_names.extend(dep_names)
        
        return class_names
    
    def _check_typescript_files_exist(
        self,
        class_names: List[str],
        output_dir: Path
    ) -> Dict[str, bool]:
        """返回依赖类型对应的 TypeScript 文件是否存在。"""
        return {
            class_name: (output_dir / f"{class_name}.ts").is_file()
            for class_name in class_names
        }
    
    def _read_typescript_file_content(self, class_name: str, output_dir: Path) -> Optional[str]:
        """读取已迁移类型；文件不存在时返回 None。"""
        ts_file = output_dir / f"{class_name}.ts"
        if not ts_file.is_file():
            return None
        return ts_file.read_text(encoding="utf-8")
    
    def _collect_migrated_typescript_code(
        self,
        class_info: Dict[str, Any],
        output_dir: Path
    ) -> str:
        """
        收集已迁移的 TypeScript 代码（优先）或 C# 源代码（后备）
        
        Args:
            class_info: 类信息字典
            output_dir: 输出目录
        
        Returns:
            代码字符串
        """
        if not class_info:
            return ""
        
        collected_code = []
        class_name = class_info.get('class_name', 'Unknown')
        
        # 优先尝试读取已迁移的 TypeScript 文件
        ts_content = self._read_typescript_file_content(class_name, output_dir)
        
        if ts_content:
            collected_code.append(f"// Migrated TypeScript code for {class_name}")
            collected_code.append(ts_content)
            collected_code.append("")
        elif "class_source_code" in class_info:
            # 后备：使用 C# 源代码
            collected_code.append(f"// C# source code for {class_name} (TypeScript file not found)")
            collected_code.append(class_info["class_source_code"])
            collected_code.append("")
        
        # 递归处理依赖类
        dependency_classes = class_info.get("dependency_classes", [])
        for dep_class in dependency_classes:
            dep_code = self._collect_migrated_typescript_code(dep_class, output_dir)
            if dep_code:
                collected_code.append(dep_code)
        
        return "\n".join(collected_code)
    
    def _remove_import_statements(self, code: str) -> str:
        """
        从代码中移除所有 import 语句，但保留 interface 和其他代码
        
        Args:
            code: TypeScript 代码
            
        Returns:
            移除 import 语句后的代码
        """
        lines = code.split('\n')
        filtered_lines = []
        
        for line in lines:
            stripped = line.strip()
            # 跳过 import 语句（包括单行和多行）
            if stripped.startswith('import '):
                continue
            # 保留其他所有代码（包括 interface、type、const、export 等）
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    def _key_to_camel_case(self, key: str) -> str:
        """
        将 key 转换为 camelCase 格式（用于导入语句中的变量名）
        
        Args:
            key: 原始 key（如 "ExpenseData", "CostCenters"）
            
        Returns:
            camelCase 格式的变量名（如 "expenseData", "costCenters"）
        """
        if not key:
            return "dataResource"
        
        key_normalized = key.strip()
        
        # 如果已经是 camelCase 或小写，直接使用
        if key_normalized[0].islower() and not re.search(r'[-_]', key_normalized):
            return key_normalized
        
        # 转换为 camelCase
        if '_' in key_normalized or '-' in key_normalized:
            # 处理下划线和连字符
            parts = re.split(r'[-_]', key_normalized)
            camel_parts = [parts[0].lower()] + [p.capitalize() for p in parts[1:] if p]
            return ''.join(camel_parts)
        else:
            # PascalCase 转 camelCase：首字母小写
            return key_normalized[0].lower() + key_normalized[1:] if len(key_normalized) > 1 else key_normalized.lower()
    
    def _generate_import_statement(self, key: str) -> str:
        """
        生成导入语句
        
        Args:
            key: 数据资源的 key（如 "ExpenseData"）
            
        Returns:
            导入语句（如 "import { expenseData } from \"./data\";"）
        """
        camel_case_name = self._key_to_camel_case(key)
        return f'import {{ {camel_case_name} }} from "./data";'
    
    async def _migrate_single_data_resource(
        self,
        data_resource: Dict[str, Any],
        output_dir: Path
    ) -> Optional[Dict[str, Any]]:
        """
        迁移单个数据资源
        
        Args:
            data_resource: 数据资源字典
            output_dir: 输出目录（用于检查已迁移的 TypeScript 文件）
        
        Returns:
            包含代码和导入信息的字典
            如果失败返回 None
        """
        source_code = data_resource.get("source_code", "")
        tag = data_resource.get("tag", "")
        key = data_resource.get("key", "")
        class_info = data_resource.get("class_info")
        
        if not source_code:
            self.logger.warning(f"数据资源 '{key}' 没有 source_code，跳过")
            return None
        
        # 检查是否有依赖的 C# 类，以及这些类是否已经迁移
        imports_needed = []
        has_cs_dependencies = False
        main_class_name = None  # 主类名（如 ExpenseReport）
        
        if class_info:
            # 获取主类名（数据资源对应的主类）
            main_class_name = class_info.get('class_name')
            
            # 收集所有依赖类名（包括主类和嵌套依赖）
            dependency_class_names = self._collect_all_dependency_class_names(class_info)
            
            if dependency_class_names:
                has_cs_dependencies = True
                # 检查这些类是否已经在 TypeScript 文件中存在
                ts_files_exist = self._check_typescript_files_exist(dependency_class_names, output_dir)
                
                # 构建导入语句（包括主类和所有依赖类）
                for class_name in dependency_class_names:
                    if ts_files_exist.get(class_name, False):
                        imports_needed.append(f"import {{ {class_name} }} from './{class_name}';")
                    else:
                        self.logger.warning(
                            f"数据资源 '{key}' 依赖的类 '{class_name}' 的 TypeScript 文件不存在，"
                            f"将创建 interface 定义"
                        )
        
        # 构建中文提示词
        uses_imported_types = bool(has_cs_dependencies and imports_needed)
        system_prompt = build_json_system_prompt(
            role="你是 WPF 数据资源到 TypeScript 的迁移专家。",
            goal="把一个 WPF 数据资源迁移为可直接并入 data.ts 的 TypeScript 源码。",
            success_criteria=(
                "保留输入中的数据层级、值和类型关系，并生成适合 React 使用的 object、array、interface 或 class instance。",
                "数据常量使用指定名称和 named export const；对象属性使用 lower camelCase，类型使用 PascalCase。",
                "复用已提供的迁移类型且不重复定义；缺失类型才根据参考源码创建最小 interface。",
                "调用已迁移 class 的 constructor 时，参数必须符合提供的真实签名。",
                "结果兼容 TypeScript 5.9.3 和 React 18.2.0。",
            ),
            constraints=(
                "typescript_code 不得包含 import；确定性流程会在保存时注入已验证的 import。",
                "不得修改指定常量名、捏造数据值、字段、类型或 constructor 参数。",
                "只定义当前数据资源实际需要且尚未提供的类型。",
            ),
            field_rules=("typescript_code 必须是完整 TypeScript 源码，不含 Markdown 代码块。",),
        )

        if key:
            expected_name = self._key_to_camel_case(key)
        else:
            base_name = self._key_to_camel_case(tag or "dataResource")
            if base_name.endswith("Provider"):
                base_name = base_name[:-len("Provider")]
            if base_name.endswith("Report"):
                base_name = base_name[:-len("Report")]
            expected_name = base_name if base_name.endswith("Data") else f"{base_name}Data"

        user_prompt_parts = [
            "请迁移以下 WPF 数据资源。",
            "",
            f"标签：{tag or '未提供'}",
            f"资源 key：{key or '未提供'}",
            f"输出常量名必须为：{expected_name}",
            "",
            "----- WPF 数据资源源码开始 -----",
            source_code,
            "----- WPF 数据资源源码结束 -----",
        ]

        if imports_needed:
            user_prompt_parts.extend([
                "",
                "以下 import 已通过确定性检查，并会在保存时自动注入；输出中不要重复写入：",
                *imports_needed,
            ])
            if main_class_name:
                user_prompt_parts.append(
                    f"优先使用 {main_class_name} 作为数据常量类型，但必须符合其真实结构。"
                )

        if class_info:
            dependency_code = self._collect_migrated_typescript_code(
                class_info,
                output_dir,
            )
            if dependency_code:
                reference_kind = "已迁移 TypeScript" if uses_imported_types else "依赖类型参考"
                user_prompt_parts.extend([
                    "",
                    f"----- {reference_kind}开始 -----",
                    dependency_code,
                    f"----- {reference_kind}结束 -----",
                ])

        user_prompt = "\n".join(user_prompt_parts)

        ts_code = await self.request_typescript_code(
            system_message=system_prompt,
            user_message=user_prompt,
        )
        if not ts_code:
            self.logger.warning(f"数据资源 '{key}' 迁移失败：无法从响应中提取代码")
            return None

        return {
            "code": ts_code,
            "imports": imports_needed,
        }
    
    @message_handler
    async def handle_data_migration_request(
        self,
        message: DataMigrationRequest,
        ctx: MessageContext
    ) -> DataMigrationResponse:
        """迁移项目数据资源。"""
        result = await self._migrate_data_resources(
            project_name=message.project_name,
            data_resources_file=message.data_resources_file,
            output_file=message.output_file
        )
        return DataMigrationResponse(**result)
    
    async def _migrate_data_resources(
        self,
        project_name: str,
        data_resources_file: str,
        output_file: str
    ) -> Dict[str, Any]:
        """
        迁移所有数据资源
        
        Args:
            project_name: 项目名称
            data_resources_file: 数据资源文件路径
            output_file: 输出文件路径
        
        Returns:
            迁移结果字典
        """
        data_resources_path = Path(data_resources_file)
        
        # 检查数据资源文件是否存在
        if not data_resources_path.exists():
            self.logger.warning(
                f"数据资源文件不存在: {data_resources_path}\n"
                f"跳过数据迁移。"
            )
            return {
                'success': False,
                'message': '数据资源文件不存在',
                'data_resources_migrated': 0,
                'data_resources_failed': 0,
                'migrated_keys': [],
                'failed_keys': [],
                'output_file': output_file
            }
        
        # 读取数据资源文件
        try:
            with open(data_resources_path, 'r', encoding='utf-8') as f:
                data_resources_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"数据资源文件格式错误: {data_resources_path}\n"
                f"JSON 解析错误: {e}"
            )
        
        # 验证必要字段
        if 'data_resources' not in data_resources_data:
            raise ValueError(
                f"数据资源文件缺少 'data_resources' 字段: {data_resources_path}"
            )
        
        data_resources = data_resources_data.get('data_resources', [])
        if not data_resources:
            self.logger.info("未找到需要迁移的数据资源")
            return {
                'success': True,
                'message': '没有数据资源需要迁移',
                'data_resources_migrated': 0,
                'data_resources_failed': 0,
                'migrated_keys': [],
                'failed_keys': [],
                'output_file': output_file
            }
        
        # 创建输出目录
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        migrated_keys = []
        failed_keys = []
        migrated_code_parts = []
        all_imports_set = set()  # 收集所有需要的导入
        data_descriptions = {}  # 收集数据描述信息，格式: {key: {ts_code: str, import_statement: str}}
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移数据资源: {project_name}")
        self.logger.info(f"数据资源总数: {len(data_resources)}")
        self.logger.info(f"输出文件: {output_path}")
        self.logger.info(f"{'='*80}\n")
        
        # 迁移每个数据资源
        for idx, data_resource in enumerate(data_resources, 1):
            key = data_resource.get("key", f"data_resource_{idx}")
            tag = data_resource.get("tag", "Unknown")
            
            self.logger.info(f"[{idx}/{len(data_resources)}] 迁移数据资源: {key} ({tag})")
            
            try:
                result = await self._migrate_single_data_resource(data_resource, output_path.parent)
                if result:
                    migrated_keys.append(key)
                    all_imports_set.update(result["imports"])
                    code = result["code"]
                    data_descriptions[key] = {
                        "ts_code": self._remove_import_statements(code),
                        "import_statement": self._generate_import_statement(key),
                    }
                    migrated_code_parts.extend([
                        f"// Data resource: {key} ({tag})",
                        code,
                        "",
                    ])
                    self.logger.info(f"  ✓ 成功迁移: {key}")
                else:
                    failed_keys.append(key)
                    self.logger.warning(f"  ✗ 迁移失败: {key}")
                    
            except Exception as e:
                failed_keys.append(key)
                self.logger.error(f"  ✗ 迁移异常: {key} - {e}")
        
        # 生成数据描述文件
        if data_descriptions:
            migration_dir = self.output_base_dir / project_name / "migration"
            migration_dir.mkdir(parents=True, exist_ok=True)
            descriptions_file = migration_dir / "data_descriptions.json"
            descriptions_file.write_text(
                json.dumps(data_descriptions, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.logger.info(f"✓ 数据描述文件已写入: {descriptions_file}")
        
        # 将所有迁移结果写入文件
        if migrated_code_parts:
            # 从生成的代码中提取使用的类型，确保所有使用的类型都有导入
            combined_code = "\n".join(migrated_code_parts)
            # 检查代码中使用的类型（正则匹配）
            # 匹配类型注解中的类型名（如 `: ExpenseReport`, `: LineItem`, `: ExpenseReport[]`）
            type_matches = re.findall(r':\s*(\w+)(?:\s*\[|\s*[=;,\[\]])', combined_code)
            # 匹配 new 关键字后的类型名（如 `new ExpenseReport`, `new LineItem`）
            new_matches = re.findall(r'new\s+(\w+)', combined_code)
            # 匹配 import 语句中的类型名（已导入的类型，需要保留）
            import_matches = re.findall(r'import\s*\{\s*(\w+)', combined_code)
            # 合并所有类型名（排除基本类型和常见关键字）
            basic_types = {'string', 'number', 'boolean', 'any', 'void', 'null', 'undefined', 'object', 'Array', 'Date', 'Function'}
            used_types = set(type_matches + new_matches + import_matches) - basic_types
            
            # 为所有使用的类型添加导入（如果文件存在）
            for type_name in used_types:
                ts_file = output_path.parent / f"{type_name}.ts"
                if ts_file.exists():
                    all_imports_set.add(f"import {{ {type_name} }} from './{type_name}';")
            
            # 构建完整的 TypeScript 文件
            file_header = [
                "// Auto-generated data file",
                f"// Migrated from WPF project: {project_name}",
                "",
                "// Data resources migrated from WPF XAML",
                "",
            ]
            
            # 添加所有导入语句（排序并去重）
            imports_section = sorted(all_imports_set)
            if imports_section:
                imports_section.append("")
            file_content = "\n".join(file_header + imports_section + migrated_code_parts)
            output_path.write_text(file_content, encoding="utf-8")
            self.logger.info(f"✓ 数据文件已写入: {output_path}")
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"数据迁移完成: {project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总数据资源数: {len(data_resources)}")
        self.logger.info(f"成功迁移: {len(migrated_keys)}")
        self.logger.info(f"迁移失败: {len(failed_keys)}")
        
        if migrated_keys:
            self.logger.info(f"\n成功迁移的数据资源:")
            for key in migrated_keys:
                self.logger.info(f"  ✓ {key}")
        
        if failed_keys:
            self.logger.warning(f"\n迁移失败的数据资源:")
            for key in failed_keys:
                self.logger.warning(f"  ✗ {key}")
        
        self.logger.info(f"{'='*80}\n")
        
        return {
            'success': not failed_keys,
            'message': '数据迁移完成' if not failed_keys else '数据迁移部分失败',
            'data_resources_migrated': len(migrated_keys),
            'data_resources_failed': len(failed_keys),
            'migrated_keys': migrated_keys,
            'failed_keys': failed_keys,
            'output_file': str(output_path)
        }
