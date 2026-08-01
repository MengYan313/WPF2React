"""
C# Migration Agent

负责迁移 C# 文件到 TypeScript，包括文件迁移、分析和 ts_info.json 管理。
"""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig, build_json_system_prompt
from src.common.source_identity import normalize_cs_id, target_relative_path
from .base import BaseMigrationAgent
from .json_schemas import TYPESCRIPT_ANALYSIS_SCHEMA
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
            llm_config = LLMConfig.json_mode_config()
        
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
        """迁移单个 C# 文件。"""
        result = await self._migrate_single_cs_file(
            file_name=message.file_name,
            cs_file_path=message.cs_file_path,
            dependencies=message.dependencies,
            defined_types=message.defined_types,
            output_dir=message.output_dir,
            ts_info_file=message.ts_info_file,
            dependency_contents={},
        )
        return CsMigrationResponse(**result)
    
    @message_handler
    async def handle_batch_cs_migration_request(
        self,
        message: BatchCsMigrationRequest,
        ctx: MessageContext
    ) -> BatchCsMigrationResponse:
        """按依赖顺序迁移项目中的 C# 文件。"""
        result = await self._migrate_batch_cs_files(
            project_name=message.project_name,
            cs_dependency_file=message.cs_dependency_file,
            output_dir=message.output_dir,
            ts_info_file=message.ts_info_file
        )
        return BatchCsMigrationResponse(**result)
    
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
        migration_order = cs_dependency_graph["migration_order"]
        files_info = cs_dependency_graph["files"]
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        migrated_files = []
        failed_files = []
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移 C# 文件: {project_name}")
        self.logger.info(f"文件总数: {len(migration_order)}")
        self.logger.info(f"目标目录: {output_path}")
        self.logger.info(f"{'='*80}\n")
        
        # 复用 Agent 自己的统一客户端；Runtime.close() 负责释放。
        if self.llm_client is None:
            raise RuntimeError("CsMigrateAgent 未配置 LLM 客户端")
        
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
                failed_files.append(file_name)
                continue
            
            cs_path = Path(cs_file_path)
            if not cs_path.exists():
                self.logger.warning(f"  跳过文件（文件不存在）: {file_name} ({cs_file_path})")
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
                            dep_ts_file = output_path / migrated_file_names[dep]
                            if dep_ts_file.exists():
                                with open(dep_ts_file, 'r', encoding='utf-8') as f:
                                    dependency_contents[dep] = f.read()
                                self.logger.debug(f"  已读取依赖文件内容: {dep} ({len(dependency_contents[dep])} 字符)")
                
                # 构建迁移 prompt
                system_prompt = self._build_cs_migration_system_prompt()
                
                user_prompt = self._build_cs_migration_user_prompt(
                    cs_source_code=cs_source_code,
                    file_name=file_name,
                    dependencies=dependencies,
                    defined_types=defined_types,
                    migrated_file_names=migrated_file_names,
                    files_info=files_info,
                    dependency_contents=dependency_contents,
                )
                
                # 调用 LLM 进行迁移
                self.logger.debug(f"  调用 LLM 迁移 C# 文件...")
                ts_code = await self.request_typescript_code(
                    system_message=system_prompt,
                    user_message=user_prompt,
                )
                if not ts_code:
                    raise ValueError(f"{file_name} 的迁移响应没有有效 TypeScript 代码")

                # 镜像仓库相对目录，只把扩展名改为 .ts。
                output_file = output_path / target_relative_path(file_name, ".ts")
                
                # 确保输出目录存在（再次检查，防止目录被删除或路径问题）
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # 保存 TypeScript 代码
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(ts_code)
                
                self.logger.debug(f"  分析 TypeScript 文件: {file_name}")
                ts_info = await self._analyze_typescript_file(
                    file_name=file_name,
                    ts_code=ts_code,
                )
                self._save_ts_info(ts_info, project_name, ts_info_file)
                self.logger.debug("  ✓ 已保存分析结果到 ts_info.json")

                migrated_files.append(file_name)
                migrated_file_names[file_name] = output_file.relative_to(output_path).as_posix()
                self.logger.info(f"  ✓ 已迁移: {file_name} -> {output_file}")
                
            except Exception as e:
                failed_files.append(file_name)
                self.logger.error(f"  ✗ 迁移失败: {file_name} - {e}", exc_info=True)
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"C# 文件迁移完成: {project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总文件数: {len(migration_order)}")
        self.logger.info(f"成功迁移: {len(migrated_files)}")
        self.logger.info(f"迁移失败: {len(failed_files)}")
        
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
            'success': not failed_files,
            'message': 'C# 文件迁移完成' if not failed_files else 'C# 文件迁移部分失败',
            'files_migrated': len(migrated_files),
            'files_failed': len(failed_files),
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
            file_name: 带扩展名的仓库相对 POSIX 源码 ID
            cs_file_path: C# 源文件路径
            dependencies: 依赖的文件名列表
            defined_types: 文件中定义的类型
            output_dir: 输出目录
            ts_info_file: ts_info.json 文件路径
            dependency_contents: 依赖文件内容字典
        
        Returns:
            迁移结果字典
        """
        file_name = normalize_cs_id(file_name)
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
            
            if self.llm_client is None:
                raise RuntimeError("CsMigrateAgent 未配置 LLM 客户端")
            
            # 构建迁移 prompt
            system_prompt = self._build_cs_migration_system_prompt()
            
            user_prompt = self._build_cs_migration_user_prompt(
                cs_source_code=cs_source_code,
                file_name=file_name,
                dependencies=dependencies,
                defined_types=defined_types,
                migrated_file_names={},
                files_info={},
                dependency_contents=dependency_contents,
            )
            
            # 调用 LLM 进行迁移
            ts_code = await self.request_typescript_code(
                system_message=system_prompt,
                user_message=user_prompt,
            )
            if not ts_code:
                error_msg = "迁移响应没有有效 TypeScript 代码"
                self.logger.error(f"{error_msg} - 文件: {file_name}")
                return {
                    'success': False,
                    'file_name': file_name,
                    'output_file': '',
                    'ts_info': None,
                    'error': error_msg
                }

            # 生成输出文件路径
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            output_file = output_path / target_relative_path(file_name, ".ts")
            
            # 确保输出目录存在（再次检查，防止目录被删除或路径问题）
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存 TypeScript 代码
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(ts_code)
            
            # 分析迁移后的 TypeScript 文件
            ts_info = await self._analyze_typescript_file(
                file_name=file_name,
                ts_code=ts_code,
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
        
        cs_dependency_graph = json.loads(cs_dep_path.read_text(encoding="utf-8"))

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
            normalize_cs_id(file_name)
            if file_name not in files:
                raise ValueError(
                    f"迁移顺序中的文件不在 files 中: {file_name}"
                )
        
        self.logger.info(f"✓ 成功加载 C# 依赖关系文件: {cs_dep_path}")
        self.logger.debug(f"  - 总文件数: {cs_dependency_graph.get('total_files', 0)}")
        self.logger.debug(f"  - 迁移顺序: {' -> '.join(migration_order)}")
        
        return cs_dependency_graph
    
    def _build_cs_migration_system_prompt(self) -> str:
        """构建 C# 到 TypeScript 的系统提示词。"""
        return build_json_system_prompt(
            role="你是 C# 到 TypeScript 的迁移专家。",
            goal="把一个 C# 文件迁移为保持业务语义、依赖正确且可直接保存的 TypeScript 文件。",
            success_criteria=(
                "保留原 C# class、interface、enum 和 struct 名称，并使用 named export。",
                "保留业务 static、继承、泛型、async 和可见的 nullable 语义。",
                "只 import 实际使用且已迁移的业务类型，路径和导出名与输入依赖一致。",
                "结果只使用项目已声明的 TypeScript API；涉及前端类型时只使用已有 React、MUI 和 Emotion API。",
            ),
            constraints=(
                "常用类型映射：string→string，数值类型→number，bool→boolean，DateTime→Date，List<T>→T[]，Dictionary<K,V>→Record<K,V>。",
                "彻底移除 INotifyPropertyChanged、PropertyChangedEventArgs、PropertyChangedEventHandler、propertyChanged event、OnPropertyChanged 及其他 WPF 专属通知逻辑。",
                "仅含 InitializeComponent、command、ShowDialog 或 UI event 的 WPF Window 不生成伪造的 TypeScript class；含业务逻辑时只提取业务部分。",
                "不得生成 React 组件，不得 import WPF 类型，不得虚构依赖或业务方法。",
                "使用 2 空格缩进、明确类型和分号。",
            ),
            field_rules=("typescript_code 必须是完整 .ts 源码，不含 Markdown 代码块。",),
        )

    def _build_cs_migration_user_prompt(
        self,
        cs_source_code: str,
        file_name: str,
        dependencies: List[str],
        defined_types: List[str],
        migrated_file_names: Dict[str, str],
        files_info: Dict[str, Any],
        dependency_contents: Dict[str, str] = None,
    ) -> str:
        """构建 C# 到 TypeScript 的用户提示词。"""
        source_id = normalize_cs_id(file_name)
        target_id = target_relative_path(source_id, ".ts").as_posix()
        dependency_text = "、".join(dependencies) if dependencies else "无"
        sections = [
            "# 任务",
            f"将源码 {source_id} 迁移为可直接保存的 {target_id}。",
            "",
            "## 当前文件合同",
            f"- 源码 ID：{source_id}",
            f"- 目标相对路径：{target_id}",
            f"- 必须保留并导出的类型：{'、'.join(defined_types) if defined_types else '以源码为准'}",
            f"- 声明的依赖文件：{dependency_text}",
        ]
        migrated_dependencies = []
        for dependency in dependencies:
            if dependency not in migrated_file_names:
                continue
            exported_types = files_info.get(dependency, {}).get("defined_types", [])
            exports = "、".join(exported_types) if exported_types else "以依赖源码为准"
            migrated_dependencies.append(
                f"- {dependency} -> {migrated_file_names[dependency]}：{exports}"
            )
        if migrated_dependencies:
            sections.extend(["", "## 已验证依赖及导出", *migrated_dependencies])
        if dependency_contents:
            sections.extend(["", "## 已迁移依赖源码"])
            for dependency, dependency_code in dependency_contents.items():
                sections.extend([
                    f"### {dependency} -> {migrated_file_names.get(dependency, target_relative_path(dependency, '.ts').as_posix())}",
                    "```typescript",
                    dependency_code,
                    "```",
                ])
        sections.extend([
            "",
            "## 待迁移 C# 源码",
            "```csharp",
            cs_source_code,
            "```",
        ])
        return "\n".join(sections)

    async def _analyze_typescript_file(
        self,
        file_name: str,
        ts_code: str,
    ) -> Dict[str, Any]:
        """
        分析迁移后的 TypeScript 文件
        
        Args:
            file_name: 带扩展名的仓库相对 POSIX 源码 ID
            ts_code: TypeScript 代码
        Returns:
            分析结果字典
        """
        if self.llm_client is None:
            raise RuntimeError("CsMigrateAgent 未配置 LLM 客户端")
        # 构建中文分析提示词
        system_prompt = build_json_system_prompt(
            role="你是 TypeScript 公共接口分析专家。",
            goal="从输入源码提取文件职责和全部 named export，供后续依赖迁移使用。",
            success_criteria=(
                "public_interfaces 覆盖源码中的每个 named export，且不包含未导出的内部符号。",
                "name 和 reference.export_name 使用精确导出名。",
                "type 取 class、interface、type、function、enum、const 或 variable。",
                "reference.import_example 给出与当前文件名一致的相对路径 named import 示例。",
            ),
            constraints=("不得虚构、重命名或遗漏源码中的 named export。",),
            field_rules=("description 和公共接口说明使用中文。",),
        )
        file_name = normalize_cs_id(file_name)
        target_id = target_relative_path(file_name, ".ts").as_posix()
        user_prompt = f"""请分析以下 TypeScript 文件。

源码 ID：{file_name}
目标相对路径：{target_id}

----- TypeScript 源码开始 -----
{ts_code}
----- TypeScript 源码结束 -----"""

        self.logger.debug("  调用 LLM 分析 TypeScript 文件...")
        analysis_result = await self.call_json(
            system_prompt,
            user_prompt,
            TYPESCRIPT_ANALYSIS_SCHEMA,
        )
        analysis_result["file_name"] = file_name
        return analysis_result
    
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
        
        data = json.loads(ts_info_path.read_text(encoding="utf-8"))
        files = data.get("files")
        if not isinstance(files, list):
            raise ValueError(f"ts_info.json 缺少 files 列表: {ts_info_path}")
        return files
    
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
