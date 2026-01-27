# -*- coding: utf-8 -*-
"""
Data Migration Agent

负责迁移项目数据资源，将 WPF XAML 数据资源转换为 TypeScript 格式供 React 使用。
"""

import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import DataMigrationRequest, DataMigrationResponse


class DataMigrateAgent(BaseMigrationAgent):
    """
    数据迁移 Agent
    
    职责：
    1. 读取 data_resources.json 文件
    2. 遍历每个数据资源，将 source_code 迁移为 TypeScript
    3. 处理依赖的 class_info 和嵌套的 dependency_classes
    4. 将所有迁移结果统一存放在 result/{project_name}/data.ts 中
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
            llm_config = LLMConfig(
                model="gpt-4o-mini",
                temperature=0,
                json_mode=False  # 数据迁移返回纯 TypeScript 代码
            )
        
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
        """
        检查 TypeScript 文件是否存在
        
        Args:
            class_names: 类名列表
            output_dir: 输出目录（result/{project_name}）
        
        Returns:
            字典，key 为类名，value 为文件是否存在
        """
        result = {}
        for class_name in class_names:
            ts_file = output_dir / f"{class_name}.ts"
            result[class_name] = ts_file.exists()
        return result
    
    def _read_typescript_file_content(self, class_name: str, output_dir: Path) -> Optional[str]:
        """
        读取已迁移的 TypeScript 文件内容
        
        Args:
            class_name: 类名
            output_dir: 输出目录（result/{project_name}）
        
        Returns:
            TypeScript 文件内容，如果文件不存在返回 None
        """
        ts_file = output_dir / f"{class_name}.ts"
        if not ts_file.exists():
            return None
        
        try:
            with open(ts_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            self.logger.warning(f"无法读取 TypeScript 文件 {ts_file}: {e}")
            return None
    
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
    
    def _extract_code_from_markers(self, response: str) -> str:
        """
        从响应中提取代码（只支持 [TypeScript Code] 标记）
        
        使用统一的标记提取工具
        
        Args:
            response: LLM 响应文本
        
        Returns:
            提取的代码字符串（已移除标记），如果未找到标记则返回原始响应
        """
        from src.migration.utils import extract_tag_content
        
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误并返回原始响应
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return response.strip()
        return result
    
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
            包含代码和导入信息的字典，格式: {'code': str, 'imports': List[str], 'main_class': str}
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
        
        # 构建 prompt
        if has_cs_dependencies and imports_needed:
            # 有依赖类且已迁移：使用导入
            system_prompt = """You are an expert at migrating WPF data resources to TypeScript for React.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all code follows TypeScript and React best practices

Your task is to convert WPF XAML data resources to TypeScript data structures suitable for React.

## Guidelines:
1. The dependency classes/types are already migrated and available via imports - DO NOT redefine them
2. Use the imported types to create data instances
3. Follow React naming conventions (camelCase for variables, PascalCase for types/interfaces)
4. **CRITICAL: Property Names MUST be lowercase camelCase**: All object property names MUST start with a lowercase letter (e.g., `alias`, `employeeNumber`, `costCenter`, `lineItems`). Do NOT use PascalCase property names (e.g., `Alias`, `EmployeeNumber`, `CostCenter`).
5. Preserve data structure and values from the XAML source
6. Create data instances that match the structure and properties of the original C# classes, but use lowercase property names
7. Export the data constant using `export const` (NOT `export default`)
8. If the main class (e.g., ExpenseReport) is imported, use it as the type annotation for the data constant
9. When creating instances of imported classes, use the correct constructor signature (check the class definition)
10. Only import classes/types that are actually used in the code
11. Remove any unused imports

## Naming Convention:
- **If a "key" is provided**: Use the key value directly as the data constant name (convert to camelCase if needed)
- **If no "key" is provided**: Use naming best practices:
  - Convert the tag/type name to camelCase (e.g., "XmlDataProvider" -> "xmlDataProvider")
  - For custom objects, use a descriptive name based on the class name (e.g., "ExpenseReport" -> "expenseData")
  - Ensure the name is descriptive and follows TypeScript/React conventions

## Important:
- DO NOT create interface/type definitions for classes that are imported
- Use the imported types directly
- Create data instances that follow the structure of the original C# classes, but **ALL property names MUST be lowercase camelCase** (e.g., `alias`, `employeeNumber`, `costCenter`, `lineItems`)
- **Example**: `const expenseData: ExpenseReport = { alias: "...", employeeNumber: "...", costCenter: "...", lineItems: ... }` (NOT `Alias`, `EmployeeNumber`, etc.)
- Use proper TypeScript type annotations (e.g., `const expenseData: ExpenseReport = {...}`)
- Match constructor signatures exactly as defined in the imported classes
- DO NOT use `export default` - use `export const` instead

## Output Format:
Output ONLY the TypeScript code, wrapped in [TypeScript Code] and [/TypeScript Code] tags.
Do NOT include markdown code blocks (```). Use the [TypeScript Code] tags instead.
"""
        else:
            # 没有依赖类或依赖类未迁移：创建 interface
            system_prompt = """You are an expert at migrating WPF data resources to TypeScript for React.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all code follows TypeScript and React best practices

Your task is to convert WPF XAML data resources (like XmlDataProvider, ObjectDataProvider, or custom objects) to TypeScript data structures suitable for React.

## Guidelines:
1. Convert XAML data to TypeScript objects/arrays/interfaces
2. Use proper TypeScript types and interfaces
3. Follow React naming conventions (camelCase for variables, PascalCase for types/interfaces)
4. **CRITICAL: Property Names MUST be lowercase camelCase**: All object property names MUST start with a lowercase letter (e.g., `alias`, `employeeNumber`, `costCenter`, `lineItems`). Do NOT use PascalCase property names (e.g., `Alias`, `EmployeeNumber`, `CostCenter`).
5. Preserve data structure and values
6. Export all types and data constants using `export const` (NOT `export default`)
7. Use proper TypeScript type annotations for data constants

## Naming Convention:
- **If a "key" is provided**: Use the key value directly as the data constant name (convert to camelCase if needed)
- **If no "key" is provided**: Use naming best practices:
  - Convert the tag/type name to camelCase (e.g., "XmlDataProvider" -> "xmlDataProvider")
  - For custom objects, use a descriptive name based on the class name (e.g., "ExpenseReport" -> "expenseData")
  - Ensure the name is descriptive and follows TypeScript/React conventions

## Output Format:
Output ONLY the TypeScript code, wrapped in [TypeScript Code] and [/TypeScript Code] tags.
Do NOT include markdown code blocks (```). Use the [TypeScript Code] tags instead.
"""
        
        # 构建用户 prompt
        user_prompt_parts = []
        
        # 如果有导入语句，在 prompt 中说明（但不添加到最终代码中，最后统一添加）
        if imports_needed:
            main_class_note = ""
            if main_class_name and main_class_name in [imp.split("import")[1].split("from")[0].strip().strip("{}") for imp in imports_needed]:
                main_class_note = f"\n- The main class '{main_class_name}' should be used as the type annotation for the data constant (e.g., `const {key}: {main_class_name} = {{...}}`)"
            
            user_prompt_parts.extend([
                "[Import Statements]",
                "The following import statements will be added to the output:",
                "\n".join(imports_needed),
                "[/Import Statements]",
                "",
                "Important Notes:",
                "- These imports are already provided, so DO NOT include them in your output code.",
                "- Just use the imported types directly in your data definitions.",
                "- Only use imported classes/types that are actually needed in your code.",
                "- When creating instances of imported classes, use the correct constructor signature.",
                "- Use proper TypeScript type annotations for the data constant.",
                main_class_note,
                ""
            ])
        
        # 构建命名说明
        import re
        
        naming_instruction = ""
        expected_name = ""
        
        if key:
            # 有 key：使用 key 的值，转换为 camelCase
            # 处理各种格式：PascalCase, snake_case, kebab-case 等
            key_normalized = key.strip()
            
            # 如果已经是 camelCase 或小写，直接使用
            if key_normalized[0].islower() and not re.search(r'[-_]', key_normalized):
                expected_name = key_normalized
            else:
                # 转换为 camelCase
                # 先处理下划线和连字符
                if '_' in key_normalized or '-' in key_normalized:
                    parts = re.split(r'[-_]', key_normalized)
                    # 将每个部分首字母大写（除了第一个）
                    camel_parts = [parts[0].lower()] + [p.capitalize() for p in parts[1:] if p]
                    expected_name = ''.join(camel_parts)
                else:
                    # PascalCase 转 camelCase：首字母小写
                    expected_name = key_normalized[0].lower() + key_normalized[1:] if len(key_normalized) > 1 else key_normalized.lower()
            
            naming_instruction = f"\n**CRITICAL NAMING REQUIREMENT**: The data constant MUST be named '{expected_name}' (derived from key '{key}')."
        else:
            # 没有 key：使用命名最佳实践
            if tag:
                # 将 tag 转换为 camelCase
                tag_normalized = tag.strip()
                if tag_normalized[0].isupper():
                    tag_camel = tag_normalized[0].lower() + tag_normalized[1:]
                else:
                    tag_camel = tag_normalized
                
                # 根据 tag 类型生成合适的名称
                if tag_normalized in ["XmlDataProvider", "ObjectDataProvider"]:
                    # XmlDataProvider -> xmlDataProvider -> 去掉 Provider -> xmlData
                    # 但实际应该根据 key 来命名，如果没有 key，使用 tag 的简化形式
                    expected_name = tag_camel.replace("Provider", "").replace("Data", "") + "Data"
                elif tag_normalized.endswith("Report"):
                    expected_name = tag_camel.replace("Report", "") + "Data"  # expenseReport -> expenseData
                elif tag_normalized.endswith("Item"):
                    expected_name = tag_camel.replace("Item", "") + "Data"  # lineItem -> lineData
                else:
                    expected_name = tag_camel + "Data"  # 默认添加 Data 后缀
                
                naming_instruction = f"\n**CRITICAL NAMING REQUIREMENT**: No 'key' provided. Use naming best practices: name the data constant '{expected_name}' (derived from tag '{tag}')."
            else:
                expected_name = "dataResource"
                naming_instruction = f"\n**CRITICAL NAMING REQUIREMENT**: No 'key' or 'tag' provided. Use descriptive camelCase naming: '{expected_name}'."
        
        # 将期望的名称添加到 prompt 中
        naming_instruction += f"\nExample: `export const {expected_name}: TypeName = {{...}};`"
        
        user_prompt_parts.extend([
            f"Migrate the following WPF data resource to TypeScript:",
            "",
            f"[Data Resource Tag]",
            tag,
            "[/Data Resource Tag]",
            "",
            f"[Data Resource Key]",
            key if key else "(not provided)",
            "[/Data Resource Key]",
            "",
            naming_instruction,
            "",
            f"[WPF Source Code]",
            source_code,
            "[/WPF Source Code]"
        ])
        
        # 如果有依赖的类信息但文件不存在，添加类源代码供参考
        if class_info and not all(self._check_typescript_files_exist(
            self._collect_all_dependency_class_names(class_info),
            output_dir
        ).values()):
            # 收集已迁移的 TypeScript 代码（优先）或 C# 源代码（后备）
            dependency_code = self._collect_migrated_typescript_code(class_info, output_dir)
            if dependency_code:
                # 检查是否包含 TypeScript 代码
                has_ts_code = any(
                    self._read_typescript_file_content(name, output_dir) is not None
                    for name in self._collect_all_dependency_class_names(class_info)
                )
                
                if has_ts_code:
                    user_prompt_parts.extend([
                        "",
                        "[Dependency Classes - Migrated TypeScript Code]",
                        "The following TypeScript code shows the migrated structure of dependency classes:",
                        "",
                        dependency_code,
                        "[/Dependency Classes - Migrated TypeScript Code]",
                        "",
                        "Use these migrated TypeScript types as reference to create matching data instances.",
                        "If interfaces/types are needed but not found in the migrated code, create them based on the structure."
                    ])
                else:
                    user_prompt_parts.extend([
                        "",
                        "[Dependency Classes - C# Source Code]",
                        "The following C# class definitions are dependencies for this data resource:",
                        "",
                        dependency_code,
                        "[/Dependency Classes - C# Source Code]",
                        "",
                        "Convert these C# classes to TypeScript interfaces/types and include them in your output."
                    ])
        elif has_cs_dependencies and imports_needed:
            # 如果有导入，提示使用导入的类型
            main_class_note = ""
            if main_class_name:
                main_class_note = f"\n- Use '{main_class_name}' as the type annotation for the data constant (e.g., `const {key}: {main_class_name} = {{...}}`)"
            
            user_prompt_parts.extend([
                "",
                "[Instructions]",
                "The dependency classes are already migrated and imported above.",
                "Use the imported types to create data instances.",
                "DO NOT redefine interfaces/types for imported classes.",
                "Create data instances that match the structure and properties of the original C# classes.",
                "",
                "CRITICAL:",
                "- Use `export const` (NOT `export default`) for data constants",
                "- Use proper TypeScript type annotations",
                "- When creating instances of imported classes, use the correct constructor signature",
                "- Only use imported classes/types that are actually needed in the code",
                "- Remove any unused imports",
                main_class_note,
                "[/Instructions]"
            ])
        
        user_prompt = "\n".join(user_prompt_parts)
        
        # 调用 LLM
        try:
            response = await self.call_llm(
                system_message=system_prompt,
                user_message=user_prompt
            )
            
            # 提取代码（移除标记）
            ts_code = self._extract_code_from_markers(response)
            
            # 确保代码中没有残留的标记
            if "[TypeScript Code]" in ts_code or "[/TypeScript Code]" in ts_code:
                # 再次尝试移除标记
                ts_code = re.sub(r'^\s*\[TypeScript\s+Code\]\s*\n?', '', ts_code, flags=re.IGNORECASE | re.MULTILINE)
                ts_code = re.sub(r'\n?\s*\[/TypeScript\s+Code\]\s*$', '', ts_code, flags=re.IGNORECASE | re.MULTILINE)
                ts_code = ts_code.strip()
            
            if not ts_code:
                self.logger.warning(f"数据资源 '{key}' 迁移失败：无法从响应中提取代码")
                return None
            
            # 不在这里添加导入语句，导入语句将在最终写入文件时统一添加
            # 返回代码和需要的导入信息（用于后续统一处理）
            return {
                'code': ts_code,
                'imports': imports_needed,
                'main_class': main_class_name
            }
            
        except Exception as e:
            self.logger.error(f"数据资源 '{key}' 迁移异常: {e}")
            return None
    
    def _collect_all_dependency_classes(self, class_info: Dict[str, Any]) -> str:
        """
        收集所有依赖类的源代码（包括嵌套依赖）
        用于当类文件不存在时，提供给 LLM 作为参考
        
        Args:
            class_info: 类信息字典，包含 class_source_code 和 dependency_classes
        
        Returns:
            所有依赖类源代码的拼接字符串
        """
        if not class_info:
            return ""
        
        collected_code = []
        
        # 添加当前类的源代码
        if "class_source_code" in class_info:
            collected_code.append(f"// {class_info.get('class_name', 'Unknown')} class")
            collected_code.append(class_info["class_source_code"])
            collected_code.append("")
        
        # 递归收集依赖类的源代码
        dependency_classes = class_info.get("dependency_classes", [])
        for dep_class in dependency_classes:
            dep_code = self._collect_all_dependency_classes(dep_class)
            if dep_code:
                collected_code.append(dep_code)
        
        return "\n".join(collected_code)
    
    @message_handler
    async def handle_data_migration_request(
        self,
        message: DataMigrationRequest,
        ctx: MessageContext
    ) -> DataMigrationResponse:
        """
        处理数据迁移请求
        
        Args:
            message: 数据迁移请求消息
            ctx: 消息上下文
        
        Returns:
            数据迁移响应消息
        """
        try:
            result = await self._migrate_data_resources(
                project_name=message.project_name,
                data_resources_file=message.data_resources_file,
                output_file=message.output_file
            )
            
            return DataMigrationResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data_resources_migrated=result.get('data_resources_migrated', 0),
                data_resources_failed=result.get('data_resources_failed', 0),
                migrated_keys=result.get('migrated_keys', []),
                failed_keys=result.get('failed_keys', []),
                output_file=result.get('output_file', '')
            )
        except Exception as e:
            return DataMigrationResponse(
                success=False,
                message=f'数据迁移失败: {str(e)}',
                data_resources_migrated=0,
                data_resources_failed=0,
                migrated_keys=[],
                failed_keys=[],
                output_file=''
            )
    
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
        
        # 记录迁移结果
        migrated_count = 0
        failed_count = 0
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
                
                if result and isinstance(result, dict) and result.get('code'):
                    migrated_count += 1
                    migrated_keys.append(key)
                    
                    # 收集导入语句
                    imports = result.get('imports', [])
                    for imp in imports:
                        all_imports_set.add(imp)
                    
                    # 提取代码（去除 import 语句，保留 interface）
                    ts_code_without_imports = self._remove_import_statements(result['code'])
                    
                    # 生成导入语句
                    import_statement = self._generate_import_statement(key)
                    
                    # 保存数据描述信息
                    data_descriptions[key] = {
                        'ts_code': ts_code_without_imports,
                        'import_statement': import_statement
                    }
                    
                    # 添加代码
                    migrated_code_parts.append(f"// Data resource: {key} ({tag})")
                    migrated_code_parts.append(result['code'])
                    migrated_code_parts.append("")
                    self.logger.info(f"  ✓ 成功迁移: {key}")
                elif result and isinstance(result, str):
                    # 兼容旧格式（字符串）
                    migrated_count += 1
                    migrated_keys.append(key)
                    
                    # 提取代码（去除 import 语句，保留 interface）
                    ts_code_without_imports = self._remove_import_statements(result)
                    
                    # 生成导入语句
                    import_statement = self._generate_import_statement(key)
                    
                    # 保存数据描述信息
                    data_descriptions[key] = {
                        'ts_code': ts_code_without_imports,
                        'import_statement': import_statement
                    }
                    
                    migrated_code_parts.append(f"// Data resource: {key} ({tag})")
                    migrated_code_parts.append(result)
                    migrated_code_parts.append("")
                    self.logger.info(f"  ✓ 成功迁移: {key}")
                else:
                    failed_count += 1
                    failed_keys.append(key)
                    self.logger.warning(f"  ✗ 迁移失败: {key}")
                    
            except Exception as e:
                failed_count += 1
                failed_keys.append(key)
                self.logger.error(f"  ✗ 迁移异常: {key} - {e}")
        
        # 生成数据描述文件
        if data_descriptions:
            migration_dir = self.output_base_dir / project_name / "migration"
            migration_dir.mkdir(parents=True, exist_ok=True)
            descriptions_file = migration_dir / "data_descriptions.json"
            
            try:
                with open(descriptions_file, 'w', encoding='utf-8') as f:
                    json.dump(data_descriptions, f, indent=2, ensure_ascii=False)
                self.logger.info(f"✓ 数据描述文件已写入: {descriptions_file}")
            except Exception as e:
                self.logger.warning(f"✗ 写入数据描述文件失败: {descriptions_file} - {e}")
        
        # 将所有迁移结果写入文件
        if migrated_code_parts:
            # 从生成的代码中提取使用的类型，确保所有使用的类型都有导入
            combined_code = "\n".join(migrated_code_parts)
            # 检查代码中使用的类型（正则匹配）
            import re
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
            imports_section = []
            if all_imports_set:
                imports_section = sorted(list(all_imports_set))  # 排序以便一致性
                imports_section.append("")  # 添加空行
            
            file_content = "\n".join(file_header + imports_section + migrated_code_parts)
            
            # 写入文件
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                self.logger.info(f"✓ 数据文件已写入: {output_path}")
            except Exception as e:
                self.logger.error(f"✗ 写入文件失败: {output_path} - {e}")
                return {
                    'success': False,
                    'message': f'写入文件失败: {e}',
                    'data_resources_migrated': migrated_count,
                    'data_resources_failed': failed_count,
                    'migrated_keys': migrated_keys,
                    'failed_keys': failed_keys,
                    'output_file': str(output_path)
                }
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"数据迁移完成: {project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总数据资源数: {len(data_resources)}")
        self.logger.info(f"成功迁移: {migrated_count}")
        self.logger.info(f"迁移失败: {failed_count}")
        
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
            'success': True,
            'message': '数据迁移完成',
            'data_resources_migrated': migrated_count,
            'data_resources_failed': failed_count,
            'migrated_keys': migrated_keys,
            'failed_keys': failed_keys,
            'output_file': str(output_path)
        }

