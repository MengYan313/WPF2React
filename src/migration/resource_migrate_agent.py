# -*- coding: utf-8 -*-
"""
Resource Migration Agent

负责迁移项目资源文件，将资源从源位置复制到目标目录。
"""

import json
import shutil
from typing import Dict, Any, List, Optional
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import ResourceMigrationRequest, ResourceMigrationResponse


class ResourceMigrateAgent(BaseMigrationAgent):
    """
    资源迁移 Agent
    
    职责：
    1. 读取 resource_dependency.json 文件
    2. 将资源文件复制到 result/{project_name}/public/ 目录
    3. 记录迁移结果
    """
    
    def __init__(
        self,
        project_name: str = "",
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化资源迁移 Agent
        
        Args:
            project_name: 项目名称（可选，可通过消息传递）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（资源迁移不需要 LLM，但保留接口一致性）
        """
        super().__init__(
            agent_type="ResourceMigrateAgent",
            llm_config=llm_config,
            output_base_dir=output_base_dir
        )
        
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
    
    @message_handler
    async def handle_resource_migration_request(
        self,
        message: ResourceMigrationRequest,
        ctx: MessageContext
    ) -> ResourceMigrationResponse:
        """
        处理资源迁移请求
        
        Args:
            message: 资源迁移请求消息
            ctx: 消息上下文
        
        Returns:
            资源迁移响应消息
        """
        try:
            result = await self._migrate_resources(
                project_name=message.project_name,
                resource_dependency_file=message.resource_dependency_file,
                resources_dir=message.resources_dir
            )
            
            return ResourceMigrationResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                resources_migrated=result.get('resources_migrated', 0),
                resources_failed=result.get('resources_failed', 0),
                migrated_files=result.get('migrated_files', []),
                failed_files=result.get('failed_files', []),
                resources_dir=result.get('resources_dir', '')
            )
        except Exception as e:
            return ResourceMigrationResponse(
                success=False,
                message=f'资源迁移失败: {str(e)}',
                resources_migrated=0,
                resources_failed=0,
                migrated_files=[],
                failed_files=[],
                resources_dir=''
            )
    
    async def _migrate_resources(
        self,
        project_name: str,
        resource_dependency_file: str,
        resources_dir: str
    ) -> Dict[str, Any]:
        """
        迁移项目资源文件
        
        根据 resource_dependency.json 文件复制资源到目标目录
        
        Args:
            project_name: 项目名称
            resource_dependency_file: 资源依赖文件路径
            resources_dir: 资源输出目录
        
        Returns:
            资源迁移结果字典
        """
        resource_dep_path = Path(resource_dependency_file)
        
        # 检查资源依赖文件是否存在
        if not resource_dep_path.exists():
            self.logger.warning(
                f"资源依赖文件不存在: {resource_dep_path}\n"
                f"跳过资源迁移。如需迁移资源，请先运行: python -m src.parser.resource_dependency"
            )
            return {
                'success': False,
                'message': '资源依赖文件不存在',
                'resources_migrated': 0,
                'resources_failed': 0,
                'migrated_files': [],
                'failed_files': [],
                'resources_dir': resources_dir
            }
        
        # 读取资源依赖文件
        try:
            with open(resource_dep_path, 'r', encoding='utf-8') as f:
                resource_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"资源依赖文件格式错误: {resource_dep_path}\n"
                f"JSON 解析错误: {e}"
            )
        
        # 验证必要字段
        if 'resources' not in resource_data:
            raise ValueError(
                f"资源依赖文件缺少 'resources' 字段: {resource_dep_path}"
            )
        
        resources = resource_data.get('resources', [])
        if not resources:
            self.logger.info("未找到需要迁移的资源文件")
            return {
                'success': True,
                'message': '没有资源需要迁移',
                'resources_migrated': 0,
                'resources_failed': 0,
                'migrated_files': [],
                'failed_files': [],
                'resources_dir': resources_dir
            }
        
        # 创建资源目录
        resources_path = Path(resources_dir)
        resources_path.mkdir(parents=True, exist_ok=True)
        
        # 记录迁移结果
        migrated_count = 0
        failed_count = 0
        migrated_files = []
        failed_files = []
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移资源文件: {project_name}")
        self.logger.info(f"资源总数: {len(resources)}")
        self.logger.info(f"目标目录: {resources_path}")
        self.logger.info(f"{'='*80}\n")
        
        # 复制每个资源文件
        for resource in resources:
            resource_path = resource.get('absolute_path')
            file_name = resource.get('file_name', '')
            exists = resource.get('exists', False)
            
            if not resource_path:
                self.logger.warning(f"  跳过资源（无绝对路径）: {file_name}")
                failed_count += 1
                failed_files.append(file_name)
                continue
            
            source_path = Path(resource_path)
            
            if not exists or not source_path.exists():
                self.logger.warning(f"  跳过资源（文件不存在）: {file_name} ({resource_path})")
                failed_count += 1
                failed_files.append(file_name)
                continue
            
            try:
                # 目标文件路径
                dest_path = resources_path / file_name
                
                # 如果目标文件已存在，先删除
                if dest_path.exists():
                    dest_path.unlink()
                
                # 复制文件
                shutil.copy2(source_path, dest_path)
                migrated_count += 1
                migrated_files.append(file_name)
                self.logger.info(f"  ✓ 已复制: {file_name} -> {dest_path}")
                
            except Exception as e:
                self.logger.error(f"  ✗ 复制失败: {file_name} - {e}")
                failed_count += 1
                failed_files.append(file_name)
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"资源迁移完成: {project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总资源数: {len(resources)}")
        self.logger.info(f"成功迁移: {migrated_count}")
        self.logger.info(f"迁移失败: {failed_count}")
        
        if migrated_files:
            self.logger.info(f"\n成功迁移的资源:")
            for file_name in migrated_files:
                self.logger.info(f"  ✓ {file_name}")
        
        if failed_files:
            self.logger.warning(f"\n迁移失败的资源:")
            for file_name in failed_files:
                self.logger.warning(f"  ✗ {file_name}")
        
        self.logger.info(f"{'='*80}\n")
        
        return {
            'success': True,
            'message': '资源迁移完成',
            'resources_migrated': migrated_count,
            'resources_failed': failed_count,
            'migrated_files': migrated_files,
            'failed_files': failed_files,
            'resources_dir': str(resources_path)
        }

