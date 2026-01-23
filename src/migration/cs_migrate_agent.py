# -*- coding: utf-8 -*-
"""
C# Migration Agent

负责迁移 C# 文件到 TypeScript，包括文件迁移、分析和 ts_info.json 管理。
"""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from autogen_core import MessageContext, message_handler, AgentId

from src.llm import LLMConfig, LLMClient
from .base import BaseMigrationAgent
from .messages import (
    CsMigrationRequest,
    CsMigrationResponse,
    BatchCsMigrationRequest,
    BatchCsMigrationResponse
)


class CsMigrateAgent(BaseMigrationAgent):
    """
    C# 文件迁移 Agent
    
    职责：
    1. 迁移单个 C# 文件到 TypeScript
    2. 批量迁移 C# 文件（按依赖顺序）
    3. 分析迁移后的 TypeScript 文件
    4. 管理 ts_info.json 文件
    """
    
    def __init__(
        self,
        project_name: str = "",
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化 C# 迁移 Agent
        
        Args:
            project_name: 项目名称（可选，可通过消息传递）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（用于 C# 迁移和文件分析）
        """
        # 如果没有提供 LLM 配置，使用默认配置
        if llm_config is None:
            llm_config = LLMConfig(
                model="gpt-4o-mini",
                temperature=0,
                json_mode=False
            )
        
        super().__init__(
            agent_type="CsMigrateAgent",
            llm_config=llm_config,
            output_base_dir=output_base_dir
        )
        
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
    
    @message_handler
    async def handle_cs_migration_request(
        self,
        message: CsMigrationRequest,
        ctx: MessageContext
    ) -> CsMigrationResponse:
        """
        处理单个 C# 文件迁移请求
        
        Args:
            message: C# 迁移请求消息
            ctx: 消息上下文
        
        Returns:
            C# 迁移响应消息
        """
        try:
            result = await self._migrate_single_cs_file(
                file_name=message.file_name,
                cs_file_path=message.cs_file_path,
                dependencies=message.dependencies,
                defined_types=message.defined_types,
                output_dir=message.output_dir,
                ts_info_file=message.ts_info_file,
                dependency_contents={}  # 单个文件迁移时，依赖内容需要从已迁移的文件中读取
            )
            
            return CsMigrationResponse(
                success=result.get('success', False),
                file_name=result.get('file_name', ''),
                output_file=result.get('output_file', ''),
                ts_info=result.get('ts_info'),
                error=result.get('error')
            )
        except Exception as e:
            return CsMigrationResponse(
                success=False,
                file_name=message.file_name,
                output_file='',
                ts_info=None,
                error=str(e)
            )
    
    @message_handler
    async def handle_batch_cs_migration_request(
        self,
        message: BatchCsMigrationRequest,
        ctx: MessageContext
    ) -> BatchCsMigrationResponse:
        """
        处理批量 C# 文件迁移请求
        
        Args:
            message: 批量 C# 迁移请求消息
            ctx: 消息上下文
        
        Returns:
            批量 C# 迁移响应消息
        """
        try:
            result = await self._migrate_batch_cs_files(
                project_name=message.project_name,
                cs_dependency_file=message.cs_dependency_file,
                output_dir=message.output_dir,
                ts_info_file=message.ts_info_file
            )
            
            return BatchCsMigrationResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                files_migrated=result.get('files_migrated', 0),
                files_failed=result.get('files_failed', 0),
                migrated_files=result.get('migrated_files', []),
                failed_files=result.get('failed_files', []),
                output_dir=result.get('output_dir', '')
            )
        except Exception as e:
            return BatchCsMigrationResponse(
                success=False,
                message=f'批量 C# 迁移失败: {str(e)}',
                files_migrated=0,
                files_failed=0,
                migrated_files=[],
                failed_files=[],
                output_dir=''
            )
    
    async def _migrate_batch_cs_files(
        self,
        project_name: str,
        cs_dependency_file: str,
        output_dir: str,
        ts_info_file: str
    ) -> Dict[str, Any]:
        """
        批量迁移 C# 文件
        
        根据 cs_dependency.json 文件按顺序迁移 C# 文件到 TypeScript
        
        Args:
            project_name: 项目名称
            cs_dependency_file: C# 依赖文件路径
            output_dir: 输出目录
            ts_info_file: ts_info.json 文件路径
        
        Returns:
            批量迁移结果字典
        """
        # 加载 C# 依赖关系图
        cs_dependency_graph = self._load_cs_dependency_graph(cs_dependency_file)
        
        if not cs_dependency_graph:
            return {
                'success': False,
                'message': 'C# 依赖文件不存在',
                'files_migrated': 0,
                'files_failed': 0,
                'migrated_files': [],
                'failed_files': [],
                'output_dir': output_dir
            }
        
        # 获取迁移顺序
        migration_order = cs_dependency_graph['migration_order']
        files_info = cs_dependency_graph.get('files', {})
        
        if not migration_order:
            self.logger.info("未找到需要迁移的 C# 文件")
            return {
                'success': True,
                'message': '没有 C# 文件需要迁移',
                'files_migrated': 0,
                'files_failed': 0,
                'migrated_files': [],
                'failed_files': [],
                'output_dir': output_dir
            }
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 记录迁移结果
        migrated_count = 0
        failed_count = 0
        migrated_files = []
        failed_files = []
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移 C# 文件: {project_name}")
        self.logger.info(f"文件总数: {len(migration_order)}")
        self.logger.info(f"目标目录: {output_path}")
        self.logger.info(f"{'='*80}\n")
        
        # 创建 LLM 客户端（用于 C# 文件迁移）
        cs_llm_config = LLMConfig(
            model=self.llm_client.config.model if self.llm_client else "gpt-4o-mini",
            temperature=0,
            json_mode=False  # C# 迁移返回纯 TypeScript 代码
        )
        cs_llm_client = LLMClient(config=cs_llm_config)
        
        # 存储已迁移的文件名（用于依赖关系）
        migrated_file_names = {}
        
        # 按顺序迁移每个 C# 文件
        total_files = len(migration_order)
        
        for idx, file_name in enumerate(migration_order, 1):
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"进度: [{idx}/{total_files}] 迁移 C# 文件: {file_name}")
            self.logger.info(f"{'='*80}\n")
            
            # 获取文件信息
            file_info = files_info.get(file_name, {})
            cs_file_path = file_info.get('cs_file', '')
            dependencies = file_info.get('dependencies', [])
            defined_types = file_info.get('defined_types', [])
            
            if not cs_file_path:
                self.logger.warning(f"  跳过文件（无源文件路径）: {file_name}")
                failed_count += 1
                failed_files.append(file_name)
                continue
            
            cs_path = Path(cs_file_path)
            if not cs_path.exists():
                self.logger.warning(f"  跳过文件（文件不存在）: {file_name} ({cs_file_path})")
                failed_count += 1
                failed_files.append(file_name)
                continue
            
            try:
                # 读取 C# 源代码
                with open(cs_path, 'r', encoding='utf-8') as f:
                    cs_source_code = f.read()
                
                self.logger.debug(f"  读取 C# 文件: {len(cs_source_code)} 字符")
                
                # 读取依赖文件的内容（如果存在）
                dependency_contents = {}
                if dependencies:
                    self.logger.debug(f"  依赖文件: {', '.join(dependencies)}")
                    # 验证依赖文件是否已成功迁移，并读取依赖文件内容
                    for dep in dependencies:
                        if dep not in migrated_file_names:
                            self.logger.warning(
                                f"  警告: 依赖文件 '{dep}' 尚未成功迁移，"
                                f"但将继续迁移 '{file_name}'"
                            )
                        else:
                            # 读取已迁移的依赖文件内容
                            dep_ts_file = output_path / f"{dep}.ts"
                            if dep_ts_file.exists():
                                with open(dep_ts_file, 'r', encoding='utf-8') as f:
                                    dependency_contents[dep] = f.read()
                                self.logger.debug(f"  已读取依赖文件内容: {dep} ({len(dependency_contents[dep])} 字符)")
                
                # 构建迁移 prompt
                system_prompt = self._build_cs_migration_system_prompt(
                    file_name=file_name,
                    dependencies=dependencies,
                    defined_types=defined_types,
                    migrated_file_names=migrated_file_names,
                    files_info=files_info,
                    dependency_contents=dependency_contents
                )
                
                user_prompt = self._build_cs_migration_user_prompt(
                    cs_source_code=cs_source_code,
                    file_name=file_name,
                    dependencies=dependencies,
                    dependency_contents=dependency_contents
                )
                
                # 调用 LLM 进行迁移
                self.logger.debug(f"  调用 LLM 迁移 C# 文件...")
                ts_code = await cs_llm_client.chat(
                    prompt=user_prompt,
                    system_message=system_prompt
                )
                
                # 清理可能的 markdown 代码块标记
                ts_code = ts_code.strip()
                if ts_code.startswith("```"):
                    lines = ts_code.split('\n')
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    ts_code = '\n'.join(lines).strip()
                
                # 生成输出文件路径
                # 保持原文件名，但扩展名改为 .ts
                output_file = output_path / f"{file_name}.ts"
                
                # 保存 TypeScript 代码
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(ts_code)
                
                migrated_count += 1
                migrated_files.append(file_name)
                migrated_file_names[file_name] = output_file.name
                
                self.logger.info(f"  ✓ 已迁移: {file_name} -> {output_file}")
                
                # 分析迁移后的 TypeScript 文件
                self.logger.debug(f"  分析 TypeScript 文件: {file_name}")
                try:
                    ts_info = await self._analyze_typescript_file(
                        file_name=file_name,
                        ts_code=ts_code,
                        cs_source_code=cs_source_code,
                        project_name=project_name,
                        ts_info_file=ts_info_file
                    )
                    # 保存分析结果到 ts_info.json
                    self._save_ts_info(ts_info, project_name, ts_info_file)
                    self.logger.debug(f"  ✓ 已保存分析结果到 ts_info.json")
                except Exception as e:
                    self.logger.warning(f"  分析 TypeScript 文件失败: {e}", exc_info=True)
                
            except Exception as e:
                failed_count += 1
                failed_files.append(file_name)
                self.logger.error(f"  ✗ 迁移失败: {file_name} - {e}", exc_info=True)
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"C# 文件迁移完成: {project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总文件数: {len(migration_order)}")
        self.logger.info(f"成功迁移: {migrated_count}")
        self.logger.info(f"迁移失败: {failed_count}")
        
        if migrated_files:
            self.logger.info(f"\n成功迁移的文件:")
            for file_name in migrated_files:
                self.logger.info(f"  ✓ {file_name}")
        
        if failed_files:
            self.logger.warning(f"\n迁移失败的文件:")
            for file_name in failed_files:
                self.logger.warning(f"  ✗ {file_name}")
        
        self.logger.info(f"{'='*80}\n")
        
        return {
            'success': True,
            'message': 'C# 文件迁移完成',
            'files_migrated': migrated_count,
            'files_failed': failed_count,
            'migrated_files': migrated_files,
            'failed_files': failed_files,
            'output_dir': str(output_path)
        }
    
    async def _migrate_single_cs_file(
        self,
        file_name: str,
        cs_file_path: str,
        dependencies: List[str],
        defined_types: List[str],
        output_dir: str,
        ts_info_file: str,
        dependency_contents: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        迁移单个 C# 文件
        
        Args:
            file_name: 文件名（不含扩展名）
            cs_file_path: C# 源文件路径
            dependencies: 依赖的文件名列表
            defined_types: 文件中定义的类型
            output_dir: 输出目录
            ts_info_file: ts_info.json 文件路径
            dependency_contents: 依赖文件内容字典
        
        Returns:
            迁移结果字典
        """
        cs_path = Path(cs_file_path)
        if not cs_path.exists():
            return {
                'success': False,
                'file_name': file_name,
                'output_file': '',
                'ts_info': None,
                'error': f'C# 文件不存在: {cs_file_path}'
            }
        
        try:
            # 读取 C# 源代码
            with open(cs_path, 'r', encoding='utf-8') as f:
                cs_source_code = f.read()
            
            # 创建 LLM 客户端
            cs_llm_config = LLMConfig(
                model=self.llm_client.config.model if self.llm_client else "gpt-4o-mini",
                temperature=0,
                json_mode=False
            )
            cs_llm_client = LLMClient(config=cs_llm_config)
            
            # 构建迁移 prompt
            system_prompt = self._build_cs_migration_system_prompt(
                file_name=file_name,
                dependencies=dependencies,
                defined_types=defined_types,
                migrated_file_names={},
                files_info={},
                dependency_contents=dependency_contents
            )
            
            user_prompt = self._build_cs_migration_user_prompt(
                cs_source_code=cs_source_code,
                file_name=file_name,
                dependencies=dependencies,
                dependency_contents=dependency_contents
            )
            
            # 调用 LLM 进行迁移
            ts_code = await cs_llm_client.chat(
                prompt=user_prompt,
                system_message=system_prompt
            )
            
            # 清理可能的代码块标记（支持 [...] 和 markdown ``` 格式）
            ts_code = ts_code.strip()
            
            # 处理 [...] 格式（优先）
            import re
            if "[TypeScript Code]" in ts_code and "[/TypeScript Code]" in ts_code:
                # 提取 [TypeScript Code] 和 [/TypeScript Code] 之间的内容
                pattern = r'\[TypeScript Code\]\s*\n(.*?)\n\[/TypeScript Code\]'
                match = re.search(pattern, ts_code, re.DOTALL)
                if match:
                    ts_code = match.group(1).strip()
            
            # 处理 markdown ``` 格式（向后兼容）
            if ts_code.startswith("```"):
                lines = ts_code.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                ts_code = '\n'.join(lines).strip()
            
            # 生成输出文件路径
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            output_file = output_path / f"{file_name}.ts"
            
            # 保存 TypeScript 代码
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(ts_code)
            
            # 分析迁移后的 TypeScript 文件
            ts_info = await self._analyze_typescript_file(
                file_name=file_name,
                ts_code=ts_code,
                cs_source_code=cs_source_code,
                project_name=self.project_name or "Unknown",
                ts_info_file=ts_info_file
            )
            
            # 保存分析结果
            self._save_ts_info(ts_info, self.project_name or "Unknown", ts_info_file)
            
            return {
                'success': True,
                'file_name': file_name,
                'output_file': str(output_file),
                'ts_info': ts_info,
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'file_name': file_name,
                'output_file': '',
                'ts_info': None,
                'error': str(e)
            }
    
    def _load_cs_dependency_graph(self, cs_dependency_file: str) -> Dict[str, Any]:
        """
        加载 C# 文件依赖关系图
        
        Args:
            cs_dependency_file: C# 依赖文件路径
        
        Returns:
            C# 依赖关系图字典（如果文件不存在则返回空字典）
        """
        cs_dep_path = Path(cs_dependency_file)
        
        if not cs_dep_path.exists():
            self.logger.warning(
                f"C# 依赖文件不存在: {cs_dep_path}\n"
                f"跳过 C# 文件迁移。如需迁移 C# 文件，请先运行: python -m src.parser.cs_dependency"
            )
            return {}
        
        with open(cs_dep_path, 'r', encoding='utf-8') as f:
            cs_dependency_graph = json.load(f)
        
        # 验证必要字段
        if 'migration_order' not in cs_dependency_graph:
            raise ValueError(
                f"C# 依赖文件缺少 'migration_order' 字段: {cs_dep_path}\n"
                f"请重新运行 C# 依赖分析以生成迁移顺序。"
            )
        
        migration_order = cs_dependency_graph['migration_order']
        if not migration_order or not isinstance(migration_order, list):
            raise ValueError(
                f"C# 依赖文件中的 'migration_order' 字段无效: {cs_dep_path}\n"
                f"期望一个非空的文件名称列表。"
            )
        
        # 验证文件信息
        if 'files' not in cs_dependency_graph:
            raise ValueError(
                f"C# 依赖文件缺少 'files' 字段: {cs_dep_path}"
            )
        
        files = cs_dependency_graph['files']
        for file_name in migration_order:
            if file_name not in files:
                self.logger.warning(
                    f"迁移顺序中包含未知文件: {file_name}，将跳过该文件"
                )
        
        self.logger.info(f"✓ 成功加载 C# 依赖关系文件: {cs_dep_path}")
        self.logger.debug(f"  - 总文件数: {cs_dependency_graph.get('total_files', 0)}")
        self.logger.debug(f"  - 迁移顺序: {' -> '.join(migration_order)}")
        
        return cs_dependency_graph
    
    def _build_cs_migration_system_prompt(
        self,
        file_name: str,
        dependencies: List[str],
        defined_types: List[str],
        migrated_file_names: Dict[str, str],
        files_info: Dict[str, Any],
        dependency_contents: Dict[str, str] = None
    ) -> str:
        """
        构建 C# 文件迁移的系统提示词
        
        Args:
            file_name: C# 文件名（不含扩展名）
            dependencies: 依赖的文件名列表
            defined_types: 文件中定义的类型（类、接口、枚举、结构体）
            migrated_file_names: 已迁移的文件名映射 {原文件名: 输出文件名}
            files_info: 文件信息字典
            dependency_contents: 依赖文件内容字典
        
        Returns:
            系统提示词
        """
        prompt = """You are an expert at migrating C# code to TypeScript.

## Version Requirements
- **TypeScript**: Use latest stable version
- **React**: Use version 19.2.0
- Ensure all code follows TypeScript best practices

## CRITICAL: File and Class Naming Requirements

**MUST maintain consistency between original C# file and migrated TypeScript file:**

1. **File Name**: The migrated TypeScript file name MUST match the original C# file name
   - Example: `LineItem.cs` → `LineItem.ts` (NOT `LineItemCollection.ts` or `lineItem.ts`)
   - Example: `EmailValidationrule.cs` → `EmailValidationrule.ts`

2. **Class/Interface/Enum Names**: All type names MUST remain exactly the same
   - Example: `public class LineItem` → `export class LineItem` (NOT `LineItemClass` or `lineItem`)
   - Example: `public interface IValidator` → `export interface IValidator`
   - Example: `public enum Status` → `export enum Status`

3. **Export Statement**: Use named exports matching the original class/interface/enum name
   - Example: `export class LineItem { ... }`
   - Example: `export interface IValidator { ... }`

## Migration Guidelines

1. **Type Conversion**:
   - `string` → `string`
   - `int`, `double`, `float` → `number`
   - `bool` → `boolean`
   - `DateTime` → `Date`
   - `List<T>` → `T[]` or `Array<T>`
   - `Dictionary<K, V>` → `Record<K, V>` or `Map<K, V>`
   - `void` → `void`
   - `object` → `any` or specific type

2. **Access Modifiers**:
   - Remove `public`, `private`, `protected` keywords (TypeScript uses visibility by default)
   - Use `private` keyword only when necessary for encapsulation
   - Use `readonly` for constants and immutable properties

3. **Properties**:
   - Convert C# properties to TypeScript properties or getter/setter
   - Example: `public string Name { get; set; }` → `name: string;` or `get name(): string { ... }`

4. **Methods**:
   - Convert C# methods to TypeScript methods
   - Handle async/await for asynchronous operations
   - Convert LINQ to array methods (map, filter, reduce, etc.)

5. **Null Safety**:
   - Use TypeScript's optional types (`?`) for nullable values
   - Example: `string?` → `string | null` or `string | undefined`

6. **Generics**:
   - Convert C# generics to TypeScript generics
   - Example: `List<T>` → `T[]` or `Array<T>`
   - Example: `Dictionary<string, int>` → `Record<string, number>`

7. **WPF-Specific Code Removal**:
   - **CRITICAL**: Remove all WPF-specific interfaces and types:
     - `INotifyPropertyChanged` → Remove interface implementation, convert to plain data class
     - `PropertyChangedEventArgs` → Remove completely, do not import or define
     - `PropertyChangedEventHandler` → Remove completely
     - `propertyChanged` events → Remove completely
     - `OnPropertyChanged` methods → Remove completely
   - **Data Classes**: Convert classes implementing `INotifyPropertyChanged` to simple TypeScript data classes:
     - Remove `INotifyPropertyChanged` interface implementation
     - Remove `propertyChanged` event handlers
     - Remove `OnPropertyChanged` methods
     - Keep only properties and business logic methods
     - Convert properties with getters/setters to simple TypeScript properties
     - Example: `public class LineItem : INotifyPropertyChanged` → `export class LineItem` (plain class with properties only)
     - Example: Properties with `OnPropertyChanged` calls should become simple properties:
       ```typescript
       // C#: public string Type { get; set; } with OnPropertyChanged("Type")
       // TypeScript: type: string;
       ```
   - Remove WPF-specific attributes (they won't be needed in React)
   - Do NOT import or reference `INotifyPropertyChanged`, `PropertyChangedEventArgs`, or any WPF-specific types from other files
   - Do NOT create interfaces or types for WPF-specific functionality

8. **Events**:
   - Remove WPF-specific event patterns (`INotifyPropertyChanged`, `PropertyChangedEventArgs`, `PropertyChangedEventHandler`)
   - For React migration, use React state management instead of property change notifications
   - Convert C# events to TypeScript event handlers or callbacks only if they are business logic events (not WPF property change events)
   - Remove event handlers related to property changes

9. **Static Members**:
   - Keep static methods and properties as static
   - Example: `public static void Method()` → `static method(): void`

10. **Inheritance**:
    - Convert C# inheritance to TypeScript class extension
    - Example: `class B : A` → `class B extends A`
    - Convert interfaces similarly

## Import Statements

When dependencies are provided, generate appropriate import statements:
- Import types/classes from dependent files using relative paths
- Example: `import { LineItem } from './LineItem';`
- Example: `import { LineItemCollection } from './LineItemCollection';`
- Use named imports matching the exported class/interface/enum names

## Output Format

**Output Format**: Output your TypeScript code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags.

[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.ts` file

## Code Style

- Use 2-space indentation
- Use semicolons
- Use meaningful variable names
- Add type annotations where helpful
- Follow TypeScript best practices
- Keep code readable and maintainable"""
        
        # 添加依赖信息
        if dependencies:
            prompt += "\n\n## Dependencies\n"
            prompt += f"This file depends on the following files: {', '.join(dependencies)}\n"
            prompt += "You MUST import the required types/classes from these files.\n"
            prompt += "Import statements should use relative paths and named imports.\n"
            prompt += "**IMPORTANT**: Do NOT import WPF-specific types (INotifyPropertyChanged, PropertyChangedEventArgs, etc.) from dependent files.\n"
            prompt += "Only import business logic types (classes, interfaces, enums) that are not WPF-specific.\n"
            prompt += "\nDependent files and their exports:\n"
            for dep in dependencies:
                if dep in migrated_file_names:
                    dep_types = files_info.get(dep, {}).get('defined_types', [])
                    if dep_types:
                        prompt += f"- `{dep}.ts`: exports {', '.join(dep_types)}\n"
                    else:
                        prompt += f"- `{dep}.ts`: exports classes/types from this file\n"
            
            # 如果有依赖文件的内容，添加到 prompt 中
            if dependency_contents:
                prompt += "\n## Dependency File Contents (for reference)\n"
                prompt += "The following are the contents of dependent files that have been migrated.\n"
                prompt += "Use these as reference to understand the structure and exports of dependencies.\n"
                prompt += "**IMPORTANT**: Do NOT import WPF-specific types (like INotifyPropertyChanged, PropertyChangedEventArgs) from these files.\n"
                prompt += "Only import business logic types (classes, interfaces, enums) that are not WPF-specific.\n\n"
                for dep, dep_content in dependency_contents.items():
                    prompt += f"[{dep}.ts]\n{dep_content}\n[/{dep}.ts]\n\n"
        
        # 添加类型信息
        if defined_types:
            prompt += f"\n## Defined Types\n"
            prompt += f"This file defines the following types: {', '.join(defined_types)}\n"
            prompt += f"These types MUST be exported with the exact same names.\n"
        
        return prompt
    
    def _build_cs_migration_user_prompt(
        self,
        cs_source_code: str,
        file_name: str,
        dependencies: List[str],
        dependency_contents: Dict[str, str] = None
    ) -> str:
        """
        构建 C# 文件迁移的用户提示词
        
        Args:
            cs_source_code: C# 源代码
            file_name: C# 文件名（不含扩展名）
            dependencies: 依赖的文件名列表
        
        Returns:
            用户提示词
        """
        prompt = f"""Migrate the following C# file to TypeScript.

## File Name
Original file: `{file_name}.cs`
Output file: `{file_name}.ts` (MUST match exactly)

## Requirements
1. Maintain the exact file name: `{file_name}.ts`
2. Maintain the exact class/interface/enum names as defined in the code
3. Convert C# syntax to TypeScript syntax following best practices
4. Add appropriate type annotations
5. Handle dependencies correctly with import statements
6. **CRITICAL - WPF Code Removal**:
   - Remove `INotifyPropertyChanged` interface implementations completely
   - Remove `PropertyChangedEventArgs` types and all usages (do not import or define)
   - Remove `PropertyChangedEventHandler` types
   - Remove `propertyChanged` event handlers
   - Remove `OnPropertyChanged` methods
   - Convert to simple data classes with properties only
   - Properties that call `OnPropertyChanged` should become simple TypeScript properties without change notifications
   - Do NOT import WPF-specific types like `INotifyPropertyChanged` or `PropertyChangedEventArgs` from other files
   - Example: `public class LineItem : INotifyPropertyChanged` → `export class LineItem` (plain class)
   - Example: Properties with `OnPropertyChanged` calls → simple properties: `type: string;`"""
        
        if dependencies:
            prompt += f"\n6. Import required types from: {', '.join(dependencies)}"
            prompt += "\n   Use relative imports: `import { TypeName } from './FileName';`"
        
        prompt += f"""

[C# Source Code]
{cs_source_code}
[/C# Source Code]

## Output Format

**Output Format**: Output your TypeScript code wrapped in `[TypeScript Code]` and `[/TypeScript Code]` tags.

[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as `{file_name}.ts`."""
        
        return prompt
    
    async def _analyze_typescript_file(
        self,
        file_name: str,
        ts_code: str,
        cs_source_code: str,
        project_name: str,
        ts_info_file: str
    ) -> Dict[str, Any]:
        """
        分析迁移后的 TypeScript 文件
        
        Args:
            file_name: 文件名（不含扩展名）
            ts_code: TypeScript 代码
            cs_source_code: 原始 C# 源代码（用于参考）
            project_name: 项目名称
            ts_info_file: ts_info.json 文件路径
        
        Returns:
            分析结果字典
        """
        # 创建用于分析的 LLM 配置（使用 JSON 模式）
        analysis_llm_config = LLMConfig(
            model=self.llm_client.config.model if self.llm_client else "gpt-4o-mini",
            temperature=0,
            json_mode=True  # 分析结果需要 JSON 格式
        )
        analysis_llm_client = LLMClient(config=analysis_llm_config)
        
        # 构建分析 prompt
        system_prompt = """You are an expert at analyzing TypeScript code.

Your task is to analyze a TypeScript file and extract:
1. File name
2. Function description (what this file does)
3. Public interfaces (exports) - classes, interfaces, types, functions, etc.
4. For each interface, provide:
   - Interface type (class, interface, type, function, enum, etc.)
   - Function description
   - How to reference/import it (export name, import statement example)

**Output your analysis wrapped in `[JSON]` and `[/JSON]` tags:**

[JSON]
{
  // Your JSON analysis here
}
[/JSON]

**Important**: Do NOT use markdown code blocks (```). Use the `[JSON]` and `[/JSON]` tags instead.

The JSON object should have the following structure:
{
  "file_name": "FileName",
  "description": "Brief description of what this file does",
  "public_interfaces": [
    {
      "name": "InterfaceName",
      "type": "class|interface|type|function|enum|const|variable",
      "description": "What this interface does",
      "reference": {
        "export_name": "InterfaceName",
        "import_example": "import { InterfaceName } from './FileName';"
      }
    }
  ]
}

Be thorough and include all exported items."""
        
        user_prompt = f"""Analyze the following TypeScript file:

[File]
{file_name}.ts
[/File]

[TypeScript Code]
{ts_code}
[/TypeScript Code]

Provide a comprehensive analysis of this file, including all public interfaces and how to use them."""
        
        # 调用 LLM 进行分析
        self.logger.debug(f"  调用 LLM 分析 TypeScript 文件...")
        analysis_json = await analysis_llm_client.chat(
            prompt=user_prompt,
            system_message=system_prompt
        )
        
        # 解析 JSON 结果（支持 [...] 和 markdown ``` 格式）
        try:
            # 清理可能的代码块标记
            cleaned_json = analysis_json.strip()
            
            # 处理 [...] 格式（优先）
            import re
            if "[JSON" in cleaned_json and "[/JSON" in cleaned_json:
                # 提取 [JSON] 和 [/JSON] 之间的内容
                pattern = r'\[JSON.*?\]\s*\n(.*?)\n\[/JSON.*?\]'
                match = re.search(pattern, cleaned_json, re.DOTALL)
                if match:
                    cleaned_json = match.group(1).strip()
            
            # 处理 markdown ``` 格式（向后兼容）
            if cleaned_json.startswith("```"):
                lines = cleaned_json.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_json = '\n'.join(lines)
            
            analysis_result = json.loads(cleaned_json)
            # 不添加 migrated_at 和 source_file 字段
            return analysis_result
        except json.JSONDecodeError as e:
            self.logger.error(f"  解析分析结果 JSON 失败: {e}")
            # 返回基本结构
            return {
                'file_name': file_name,
                'description': 'Analysis failed',
                'public_interfaces': [],
                'error': str(e)
            }
    
    def _load_ts_info(self, ts_info_file: str) -> List[Dict[str, Any]]:
        """
        加载 ts_info.json 文件
        
        Args:
            ts_info_file: ts_info.json 文件路径
        
        Returns:
            文件信息列表
        """
        ts_info_path = Path(ts_info_file)
        
        if not ts_info_path.exists():
            return []
        
        try:
            with open(ts_info_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 如果文件是列表格式，直接返回
                if isinstance(data, list):
                    return data
                # 如果文件是对象格式，尝试获取 files 字段
                elif isinstance(data, dict) and 'files' in data:
                    return data['files']
                else:
                    return []
        except Exception as e:
            self.logger.warning(f"加载 ts_info.json 失败: {e}")
            return []
    
    def _save_ts_info(
        self,
        file_info: Dict[str, Any],
        project_name: str,
        ts_info_file: str
    ):
        """
        保存文件信息到 ts_info.json（追加模式）
        
        Args:
            file_info: 文件信息字典
            project_name: 项目名称
            ts_info_file: ts_info.json 文件路径
        """
        # 确保目录存在
        ts_info_path = Path(ts_info_file)
        ts_info_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载现有数据
        existing_files = self._load_ts_info(ts_info_file)
        
        # 检查是否已存在该文件的信息，如果存在则更新，否则追加
        file_name = file_info.get('file_name', '')
        updated = False
        for i, existing_file in enumerate(existing_files):
            if existing_file.get('file_name') == file_name:
                existing_files[i] = file_info
                updated = True
                break
        
        if not updated:
            existing_files.append(file_info)
        
        # 保存到文件
        output_data = {
            'project_name': project_name,
            'total_files': len(existing_files),
            'files': existing_files
        }
        
        with open(ts_info_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        self.logger.debug(f"  已更新 ts_info.json: {file_name}")

