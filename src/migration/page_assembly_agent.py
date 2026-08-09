"""
Page Assembly Agent

负责将已迁移的根组件整合成完整的 React 页面。
"""

import os
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig, build_json_system_prompt
from src.common.source_identity import target_relative_path
from .base import BaseMigrationAgent
from .messages import PageAssemblyRequest, PageAssemblyResponse
from .utils import (
    ensure_correct_export_name,
    get_available_resources,
    get_page_depended_by_count,
    log_code_output,
    read_file_content,
    save_tsx_file,
    validate_generated_tsx,
)


class PageAssemblyAgent(BaseMigrationAgent):
    """
    页面整合 Agent
    
    职责：
    1. 接收已迁移的根组件代码
    2. 通过多轮渐进式修改整合成完整的 React 页面（按执行顺序）：
       - 第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面，确保函数签名格式正确
       - 第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
       - 第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑（可选）
       - 第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑（可选）
       - 第五轮：布局优化 - 确保整体布局正确，优化页面结构
       - 第六轮：子页面集成 - 确保子页面引用正确，集成子组件
       - 第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
    3. 返回完整的页面代码
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        result_dir: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化页面整合 Agent
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            result_dir: 最终产物目录；默认 results/{project_name}
            llm_config: LLM 配置（默认使用低档模型，非 JSON 模式）
        """
        # 初始化基类（页面整合不需要 JSON 模式）
        super().__init__(
            agent_type="PageAssemblyAgent",
            llm_config=llm_config or LLMConfig.json_mode_config(),
            output_base_dir=output_base_dir
        )
        
        # 项目配置
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        
        # 目录路径
        self.dependency_dir = self.output_base_dir / project_name / "dependency"
        self.result_dir = Path(result_dir) if result_dir else Path("results") / project_name
        self.resources_dir = self.result_dir / "public"  # 资源文件目录
    
    @message_handler
    async def handle_assembly_request(
        self,
        message: PageAssemblyRequest,
        ctx: MessageContext
    ) -> PageAssemblyResponse:
        """执行七轮页面组装。"""
        result = await self._assemble_page(
            page_id=message.page_id,
            page_name=message.component_name,
            page_source=message.page_source,
            root_component=message.root_component,
            page_layout_description=message.page_layout_description,
            child_page_references=message.child_page_references,
            direct_dependencies=message.direct_dependencies,
            template=message.template,
            data=message.data
        )
        return PageAssemblyResponse(**result)
    
    async def _assemble_page(
        self,
        page_id: str,
        page_name: str,
        page_source: str,
        root_component: str,
        page_layout_description: str,
        child_page_references: str,
        direct_dependencies: List[str],
        template: str = "",
        data: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        页面整合阶段：将根组件整合成完整的 React 页面（多轮渐进式修改）
        
        Args:
            page_id: 页面唯一 ID
            page_name: 组件符号（最终导出的组件名必须与此相同）
            page_source: 完整的 WPF 页面源代码（XAML）
            root_component: 根组件的迁移代码
            page_layout_description: 页面布局描述
            child_page_references: 子页面引用分析
            direct_dependencies: 直接依赖页面列表
            
        Returns:
            整合后的页面代码字典
        """
        self.logger.info(f"开始页面整合: {page_id} ({page_name})")
        
        # 获取可用的资源文件列表
        available_resources = get_available_resources(self.resources_dir)
        self.logger.debug(f"  可用资源文件: {available_resources}")
        
        # 创建临时文件路径用于存储每一轮的结果
        target_tsx_path = self.result_dir / target_relative_path(page_id, ".tsx")
        temp_tsx_path = target_tsx_path.with_name(f"{target_tsx_path.stem}_temp.tsx")
        temp_tsx_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = data or {}

        depended_by_count = get_page_depended_by_count(
            self.dependency_dir / "page_dependency.json",
            page_id,
            self.logger,
        )
        if depended_by_count is not None:
            is_root_page = depended_by_count == 0
        else:
            is_root_page = page_name == "MainWindow"
        expected_props = [] if is_root_page else ["open", "onClose"]
        required_data_identifiers = []
        import_match = re.search(
            r"\bimport\s*\{([^}]*)\}", str(data.get("import_statement", ""))
        )
        if import_match:
            required_data_identifiers = [
                item.split(" as ", 1)[-1].strip()
                for item in import_match.group(1).split(",")
                if item.strip()
            ]
        object_data_identifiers = [
            identifier
            for identifier in required_data_identifiers
            if re.search(
                rf"\bexport\s+const\s+{re.escape(identifier)}\s*=\s*\{{",
                str(data.get("ts_code", "")),
            )
        ]
        
        # 构建依赖页面导入说明（用于 prompt）
        dependency_imports_text = ""
        if direct_dependencies:
            dependency_imports_list = []
            dependency_graph = {}
            dependency_file = self.dependency_dir / "page_dependency.json"
            if not dependency_file.exists():
                raise FileNotFoundError(f"页面依赖产物不存在: {dependency_file}")
            import json
            dependency_graph = json.loads(dependency_file.read_text(encoding="utf-8"))
            dependency_pages = dependency_graph.get("pages", {})
            for dep in direct_dependencies:
                dep_file = self.result_dir / target_relative_path(dep, ".tsx")
                dep_info = dependency_pages.get(dep)
                if not isinstance(dep_info, dict):
                    raise ValueError(f"页面依赖产物缺少直接依赖: {dep}")
                dep_component = dep_info.get("component_name")
                if not dep_component:
                    raise ValueError(f"直接依赖 {dep} 缺少 component_name")
                if dep_file.exists():
                    dependency_imports_list.append(
                        f"- {dep}（组件 {dep_component}）: Available ({dep_file})"
                    )
                else:
                    dependency_imports_list.append(
                        f"- {dep}（组件 {dep_component}）: NOT AVAILABLE ({dep_file})"
                    )
            dependency_imports_text = "\n".join(dependency_imports_list)
        else:
            dependency_imports_text = "None"
        
        # 构建资源信息部分
        resources_section = ""
        if available_resources:
            resources_list = "\n".join([f"  - {res}" for res in available_resources])
            resources_section = f"""
Available Resources (in public/ directory):
{resources_list}

Note: Reference these resources using absolute paths starting with `/`, e.g., `/Watermark.png`
"""
        
        # ========== 多轮渐进式修改 ==========
        # 执行顺序：1.初始组装 2.资源修复 3.模板整合 4.数据整合 5.布局优化 6.子页面集成 7.代码规范
        
        # 在初始组装前，记录迁移后的根组件代码
        self.logger.info(f"  迁移后的根组件代码:")
        log_code_output("迁移后的根组件", page_name, root_component, self.logger)
        
        # 第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面，确保函数签名格式正确
        self.logger.info(f"  第一轮：初始组装...")
        page_code = await self._assemble_round_1_initial(
            page_id=page_id,
            page_name=page_name,
            component_code=root_component
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第一轮：初始组装完成")
        log_code_output("第一轮：初始组装", page_name, page_code, self.logger)
        
        # 第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
        if available_resources:
            page_code = await self._run_assembly_round(
                "第二轮：资源修复", temp_tsx_path, page_name,
                self._assemble_round_2_resources(
                    page_name=page_name,
                    resources_section=resources_section,
                    temp_tsx_path=temp_tsx_path,
                ),
            )
        else:
            self.logger.debug("  第二轮：资源修复（跳过：无资源文件）")

        # 第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑（如果存在）
        if template.strip():
            page_code = await self._run_assembly_round(
                "第三轮：模板整合", temp_tsx_path, page_name,
                self._assemble_round_3_template(
                    page_name=page_name,
                    template_code=template,
                    temp_tsx_path=temp_tsx_path,
                ),
            )
        else:
            self.logger.debug("  第三轮：模板整合（跳过：无模板依赖）")

        # 第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑（如果存在且包含必要信息）
        if data:
            missing_fields = {"ts_code", "import_statement"} - data.keys()
            if missing_fields:
                raise ValueError(
                    f"数据依赖缺少字段: {', '.join(sorted(missing_fields))}"
                )
            page_code = await self._run_assembly_round(
                "第四轮：数据整合", temp_tsx_path, page_name,
                self._assemble_round_4_data(
                    page_name=page_name,
                    data_info=data,
                    temp_tsx_path=temp_tsx_path,
                ),
            )
        else:
            self.logger.debug("  第四轮：数据整合（跳过：无数据依赖）")

        # 第五轮：布局优化 - 确保整体布局正确，优化页面结构
        page_code = await self._run_assembly_round(
            "第五轮：布局优化", temp_tsx_path, page_name,
            self._assemble_round_5_layout(
                page_name=page_name,
                page_source=page_source,
                page_layout_description=page_layout_description,
                temp_tsx_path=temp_tsx_path,
            ),
        )

        # 第六轮：子页面集成 - 确保子页面引用正确，集成子组件
        page_code = await self._run_assembly_round(
            "第六轮：子页面集成", temp_tsx_path, page_name,
            self._assemble_round_6_child_pages(
                page_name=page_name,
                child_page_references=child_page_references,
                dependency_imports_text=dependency_imports_text,
                direct_dependencies=direct_dependencies,
                temp_tsx_path=temp_tsx_path,
            ),
        )

        # 第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
        page_code = await self._run_assembly_round(
            "第七轮：代码规范", temp_tsx_path, page_name,
            self._assemble_round_7_code_style(
                page_name=page_name,
                is_root_page=is_root_page,
                available_local_modules=self._available_local_modules(target_tsx_path),
                temp_tsx_path=temp_tsx_path,
            ),
        )
        
        # 最终清理和验证
        self.logger.debug(f"  最终清理和验证...")
        page_code = ensure_correct_export_name(page_code, page_name, self.logger)
        validation_errors = validate_generated_tsx(
            page_name,
            page_code,
            expected_props=expected_props,
            required_data_identifiers=required_data_identifiers,
            object_data_identifiers=object_data_identifiers,
            source_file=target_tsx_path,
        )
        if validation_errors:
            raise ValueError(
                "最终 TSX 静态验证失败: " + "; ".join(validation_errors)
            )
        self.logger.debug(f"  ✓ 最终清理和验证完成")
        log_code_output("最终清理和验证", page_name, page_code, self.logger)
        
        # 删除临时文件
        temp_tsx_path.unlink(missing_ok=True)
        
        # 构建整合说明（按实际执行顺序）
        rounds_list = [
            "初始组装",
        ]
        if available_resources:
            rounds_list.append("资源修复")
        if template.strip():
            rounds_list.append("模板整合")
        if data:
            rounds_list.append("数据整合")
        rounds_list.extend([
            "布局优化",
            "子页面集成",
            "代码规范",
        ])
        
        rounds_text = " → ".join(rounds_list)
        
        self.logger.info(f"✓ 页面整合完成: {page_id} ({page_name}) (共 {len(rounds_list)} 轮: {rounds_text})")
        
        return {
            "page_code": page_code,
            "page_description": f"{page_id}（{page_name}）的完整 React 页面",
            "assembly_notes": (
                f"页面经过 {len(rounds_list)} 轮组装：{rounds_text}。"
                f"导出名为 {page_name}。"
            )
        }

    async def _run_assembly_round(
        self,
        label: str,
        temp_tsx_path: Path,
        page_name: str,
        round_coro,
    ) -> str:
        """
        执行一个渐进式整合轮次（第 2~7 轮通用的样板逻辑）。

        此前第 2~7 轮各自重复了完全相同的"调用 → 空响应回退 → 保存 → 记录"
        六行代码。这里集中实现，日志文案、回退语义（解析失败时回退到上一轮
        的临时文件内容）与原逐轮实现逐字一致，因此不改变整合行为。

        第一轮（初始组装）是种子轮，没有"上一轮临时文件"可回退，故不走此路径。

        Args:
            label: 轮次中文标签，如 "第二轮：资源修复"
            temp_tsx_path: 跨轮共享的临时 tsx 文件路径
            page_name: 页面名（用于保存与日志）
            round_coro: 该轮的协程（在调用处构造，此处 await 执行）

        Returns:
            本轮产出的页面代码；若 LLM 响应解析失败则为上一轮临时文件内容
        """
        self.logger.info(f"  {label}...")
        page_code = await round_coro
        # 如果返回空字符串，使用上一轮的结果
        if not page_code or page_code.strip() == "":
            self.logger.warning(f"  {label} - LLM 响应解析失败，使用上一轮结果")
            page_code = read_file_content(temp_tsx_path)
        else:
            save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ {label}完成")
        log_code_output(label, page_name, page_code, self.logger)
        return page_code

    async def _assemble_round_1_initial(
        self,
        page_id: str,
        page_name: str,
        component_code: str
    ) -> str:
        """第一轮：只纠正组件名、函数签名和默认导出。"""
        dependency_file = self.dependency_dir / "page_dependency.json"
        depended_by_count = get_page_depended_by_count(
            dependency_file,
            page_id,
            self.logger,
        )
        if depended_by_count is not None:
            is_main_window = depended_by_count == 0
            page_kind = "根页面" if is_main_window else "子页面"
            self.logger.info(
                f"  页面类型判断（基于依赖信息）: {page_name} - {page_kind} "
                f"(depended_by_count={depended_by_count})"
            )
        else:
            is_main_window = page_name == "MainWindow"
            self.logger.info(
                f"  页面类型判断（基于名称匹配）: {page_name} - "
                f"{'根页面' if is_main_window else '子页面'}"
            )

        signature_requirement = self._page_signature_requirement(
            page_name,
            is_main_window,
        )

        system_prompt = build_json_system_prompt(
            role="你是 React 与 TypeScript 组件合同修订专家。",
            goal="只纠正组件名、函数签名和默认导出，不改变组件行为。",
            success_criteria=(
                signature_requirement,
                f"文件末尾为 export default {page_name};。",
                "结果只使用项目已声明的 React、MUI、Emotion 和 TypeScript API。",
            ),
            constraints=(
                "不得修改 import、业务逻辑、interface 内容、event handler 或 TSX 结构。",
                "不得新增其他 props、组件或依赖。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请按上述要求修订组件。

页面名：{page_name}

----- 当前组件源码开始 -----
{component_code}
----- 当前组件源码结束 -----"""
        return await self.request_typescript_code(system_prompt, user_prompt)

    @staticmethod
    def _page_signature_requirement(page_name: str, is_root_page: bool) -> str:
        if is_root_page:
            return f"""组件必须使用：
export function {page_name}() {{
  // 保留原组件实现
}}
不得声明或接收 Props，不得使用 React.FC。"""
        return f"""组件必须精确使用：
interface {page_name}Props {{
  open: boolean;
  onClose: () => void;
}}

export function {page_name}({{ open, onClose }}: {page_name}Props) {{
  // 保留原组件实现
}}
不得增加其他 props，不得改为 props 对象参数或 React.FC。"""

    def _available_local_modules(self, target_file: Path) -> List[str]:
        modules = []
        for pattern in ("*.ts", "*.tsx"):
            for path in self.result_dir.rglob(pattern):
                if path == target_file or path.stem.endswith("_temp"):
                    continue
                module = Path(
                    os.path.relpath(path.with_suffix(""), target_file.parent)
                ).as_posix()
                modules.append(module if module.startswith(".") else f"./{module}")
        return sorted(set(modules))

    async def _assemble_round_2_resources(
        self,
        page_name: str,
        resources_section: str,
        temp_tsx_path: Path
    ) -> str:
        """第二轮：只修复静态资源引用。"""
        current_code = read_file_content(temp_tsx_path)
        system_prompt = build_json_system_prompt(
            role="你是 React 静态资源路径修复专家。",
            goal="只修复当前 TSX 中能够由可用资源清单确认的静态资源引用。",
            success_criteria=(
                "public/ 下文件使用 /filename.ext 形式。",
                "移除 ./public/filename、占位路径和无必要的 process.env.PUBLIC_URL。",
                "所有修改后的资源路径都能对应输入的可用资源。",
            ),
            constraints=(
                "只做资源路径所需的最小修改。",
                "保留组件名、函数签名、import、export、布局和业务逻辑。",
                "不得虚构资源文件。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请修复以下组件的静态资源引用。

页面名：{page_name}

## 可用资源
{resources_section}

## 当前完整 TSX
----- TSX 开始 -----
{current_code}
----- TSX 结束 -----"""
        return await self.request_typescript_code(system_prompt, user_prompt)

    async def _assemble_round_3_template(
        self,
        page_name: str,
        template_code: str,
        temp_tsx_path: Path
    ) -> str:
        """第三轮：整合可迁移的模板结构与格式。"""
        current_code = read_file_content(temp_tsx_path)
        system_prompt = build_json_system_prompt(
            role="你是 React 组件模板整合专家。",
            goal="把 WPF DataTemplate/ControlTemplate 中可可靠映射的结构补入当前 TSX。",
            success_criteria=(
                "只补充当前组件确实遗漏的渲染结构、layout、style 和 binding。",
                "新增结构复用现有代码的 MUI 组件和命名。",
                "无法可靠映射、无效或无关的模板内容被忽略。",
            ),
            constraints=(
                "只在新增结构确有需要时添加合法 import。",
                "保留业务逻辑、组件名、函数签名和默认导出。",
                "不得从模板推断输入中不存在的业务行为。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请把可迁移的模板信息整合到当前组件。

页面名：{page_name}

## WPF 模板
----- 模板开始 -----
{template_code}
----- 模板结束 -----

## 当前完整 TSX
----- TSX 开始 -----
{current_code}
----- TSX 结束 -----"""
        return await self.request_typescript_code(system_prompt, user_prompt)

    async def _assemble_round_4_data(
        self,
        page_name: str,
        data_info: Dict[str, Any],
        temp_tsx_path: Path
    ) -> str:
        """第四轮：按已迁移数据的精确结构整合数据资源。"""
        current_code = read_file_content(temp_tsx_path)
        if not (
            "ts_code" in data_info
            and "import_statement" in data_info
        ):
            self.logger.warning(
                "  数据整合跳过：缺少 ts_code 或 import_statement"
            )
            return current_code

        import_statement = str(data_info.get("import_statement", ""))
        data_code = str(data_info.get("ts_code", ""))
        system_prompt = build_json_system_prompt(
            role="你是 React 数据资源整合专家。",
            goal="按已迁移数据的精确合同，把数据资源接入当前 TSX。",
            success_criteria=(
                "原样加入给定 import，并在组件中实际使用对应数据。",
                "常量名、类型名、对象属性名和访问路径与给定 TypeScript 源码完全一致。",
                "object 先访问其真实 array 属性，再调用 map、reduce 或 filter。",
            ),
            constraints=(
                "不得创建假数据、重命名字段、虚构 getter 或猜测未提供的数据结构。",
                "只做数据接入所需修改，保留组件名、函数签名、布局、子页面交互和默认导出。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请把数据资源整合到当前组件。

页面名：{page_name}

## 必须加入的 import
{import_statement}

## 数据资源的精确 TypeScript 结构
----- data.ts 片段开始 -----
{data_code}
----- data.ts 片段结束 -----

## 当前完整 TSX
----- TSX 开始 -----
{current_code}
----- TSX 结束 -----"""
        return await self.request_typescript_code(system_prompt, user_prompt)

    async def _assemble_round_5_layout(
        self,
        page_name: str,
        page_source: str,
        page_layout_description: str,
        temp_tsx_path: Path,
    ) -> str:
        """第五轮：对照 XAML 修复页面整体布局。"""
        current_code = read_file_content(temp_tsx_path)
        system_prompt = build_json_system_prompt(
            role="你是 React 与 TypeScript 页面布局修复专家。",
            goal="对照原始 XAML 和布局分析，只修复当前 TSX 遗漏或错误的整体布局。",
            success_criteria=(
                "主要区域、层级、排列、对齐和尺寸关系与输入证据一致。",
                "网格使用 Box + CSS Grid/Flexbox，简单行列使用 Stack。",
                "结果只使用项目已声明的 React、MUI 和 TypeScript API。",
            ),
            constraints=(
                "禁止使用 MUI Grid。",
                "不得 import 未提供的本地组件；删除无效本地 import，确有需要时才就地实现。",
                "只做布局所需修改，保留业务逻辑、交互、组件名、函数签名、Props、数据、子页面整合和默认导出。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请对照 WPF 页面修复当前 React 布局。

页面名：{page_name}

## 原始 XAML
----- XAML 开始 -----
{page_source}
----- XAML 结束 -----

## 布局分析
{page_layout_description}

## 当前完整 TSX
----- TSX 开始 -----
{current_code}
----- TSX 结束 -----"""
        return await self.request_typescript_code(system_prompt, user_prompt)

    async def _assemble_round_6_child_pages(
        self,
        page_name: str,
        child_page_references: str,
        dependency_imports_text: str,
        direct_dependencies: List[str] = None,
        temp_tsx_path: Path = None
    ) -> str:
        """第六轮：整合所有直接依赖的子页面与交互。"""
        current_code = read_file_content(temp_tsx_path)
        direct_deps_text = "\n".join(direct_dependencies) if direct_dependencies else "无"
        system_prompt = build_json_system_prompt(
            role="你是 React 子页面交互整合专家。",
            goal="接入全部已确认的直接依赖子页面，并补全触发和关闭交互。",
            success_criteria=(
                "加入给定的全部子页面 import，且每个直接依赖组件在最终 TSX 中实际使用。",
                "每个 Dialog 使用独立 useState，并正确传递 open/onClose。",
                "Button、IconButton、MenuItem、Select 和表单按钮引用的 event handler 均已声明且行为明确。",
            ),
            constraints=(
                "不得虚构未列出的子页面、import、导航目标或业务交互。",
                "只做子页面与交互所需的最小修改，保留布局、数据逻辑、组件名、函数签名和默认导出。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请整合以下子页面及交互。

页面名：{page_name}

## 子页面 import
{dependency_imports_text or '无'}

## 直接依赖
{direct_deps_text}

## 子页面引用分析
{child_page_references}

## 当前完整 TSX
----- TSX 开始 -----
{current_code}
----- TSX 结束 -----

典型交互应类似：
const [dialogOpen, setDialogOpen] = useState(false);
<Button onClick={{() => setDialogOpen(true)}}>打开</Button>
<ChildDialog open={{dialogOpen}} onClose={{() => setDialogOpen(false)}} />"""
        return await self.request_typescript_code(system_prompt, user_prompt)

    async def _assemble_round_7_code_style(
        self,
        page_name: str,
        is_root_page: bool,
        available_local_modules: List[str],
        temp_tsx_path: Path
    ) -> str:
        """第七轮：执行不改变行为的最终代码整理。"""
        current_code = read_file_content(temp_tsx_path)
        system_prompt = build_json_system_prompt(
            role="你是 React 与 TypeScript 代码质量整理专家。",
            goal="在不改变行为的前提下，完成当前 TSX 的最终结构和引用整理。",
            success_criteria=(
                "代码顺序为 React import → MUI import → 子页面 import → 数据 import → 其他 import → interface/type → utility → 主组件 → 默认导出。",
                "去重 import，并只删除能够确定未使用的 import、interface、type 和变量。",
                "所有引用均已声明，event handler 使用清楚名称；组件内部没有与组件同名的变量或函数。",
                "本地 import 只能引用下方列出的已存在模块；移除虚构的本地 import，并在当前文件内保留其所需的最小实现。",
                f"组件名为 {page_name}，文件末尾为 export default {page_name};。",
                self._page_signature_requirement(page_name, is_root_page),
            ),
            constraints=(
                "禁止修改已经正确的函数签名、Props 合同、布局、数据访问、业务逻辑和子页面交互。",
                "不得借整理之机新增功能或重构组件边界。",
            ),
            field_rules=("typescript_code 必须是完整 TSX 源码，不含 Markdown 代码块。",),
        )
        user_prompt = f"""请整理以下完整 TSX。

页面名：{page_name}

已存在的本地模块：
{chr(10).join(available_local_modules) or '无'}

----- TSX 开始 -----
{current_code}
----- TSX 结束 -----"""
        return await self.request_typescript_code(system_prompt, user_prompt)
