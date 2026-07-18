# WPF2React 本地开发基线

更新时间：2026-07-17
基线提交：`54e23ffd5c58`（`master` 与 `origin/master` 同步）
适用工作区：`/Users/sophon/Codex/WPF2React`

## 1. 范围与原则

初始化阶段建立了可重复开发环境并验证仓库现有流程。2026-07-17 在不改变迁移方法、Agent 数量、检索方式、页面组装轮次或目标前端版本的前提下，进一步统一目录结构、模型档位配置并补充合成输入 smoke 测试。

`02_前端UI迁移研究稿.md` 和 `03_面向代码可复用性增强的融合研究方案.md` 是后续科研与实验背景，不是当前代码必须立即满足的规格。前者提出未来 MigraUI 三阶段路线、基线、六个核心消融和指标；后者说明 UI 迁移与 C++ 代码复用研究共享总目标和方法背景，但两个代码库、数据流和工程仍独立。

## 2. 主机、Git 与原有工具

- 系统：macOS 26.5.2，Apple Silicon `arm64`。
- 原有系统命令：`/usr/bin/python3` 报告 Python 3.9.6，实际 executable 为 Command Line Tools 下的 Python。未替换、未修改、未向其中安装包。
- 初始化前没有 `conda`、`pyenv` 或 `uv`。仓库文档中的 `/home/wenxinyao/...` 与 `/home/wenxinyao/anaconda3/envs/autogen` 是旧 Linux 机器路径，本机不可用。
- Homebrew 5.1.14 已存在。
- Node.js：`v23.11.0`；npm：`11.6.2`。满足 README 的 Node 18+ 下限，但不是 LTS 基线，也不等于提示词中固定的 React/MUI 包版本。
- 未安装 `dotnet`。四个示例 `.csproj` 均以 `net10.0-windows` 为目标；WPF 应用不能在本机 macOS 上直接运行。`ExpenseItDemo.csproj` 还引用仓库中不存在的 `../EditBoxControlLibrary/EditBoxControlLibrary.csproj`。
- 远端：`ssh://git@ssh.github.com:443/MengYan313/WPF2React.git`。`docs/GIT_WORKFLOW.md` 中旧目录和“首次推送”描述已过时。
- 初始化前无 `outputs/`、`results/`、`logs/` 和 `.env`；Git 仅有用户复制进来的 `AGENTS.md` 与两份研究文档处于未跟踪状态。

## 3. Python 版本判断

候选版本：

- Python 3.10：满足当前最低实际语法和核心依赖要求，但支持周期与可复现余量短于 3.11。
- Python 3.11：满足实际语法、仓库文档推荐上限和全部关键依赖；tree-sitter、tree-sitter-c-sharp、lxml 等均有 macOS arm64 二进制轮子。选为最终版本。
- Python 3.12：核心依赖大概率可用，但超出仓库原文“推荐 3.8-3.11”的验证范围，对复现原流程没有额外收益。

初始化时 README/DEPENDENCIES 声称 Python 3.8+，但实际最低版本是 3.10：

- `src/migration/messages.py` 使用 `str | None`（PEP 604，Python 3.10+）。
- `src/logger.py`、`src/parser/wpf_base_controls.py` 使用内置泛型注解。
- 已安装的 `autogen-core 0.7.5`、`autogen-ext 0.7.5`、`sentence-transformers 5.2.0`、`tree-sitter 0.25.2` 均声明 `Requires-Python >=3.10`。

最终选择：Homebrew Python 3.11.12。没有发生 Python 版本回退。

## 4. 安装与复现

解释器以并行、非破坏方式通过 `brew install python@3.11` 安装：

- Homebrew formula：`python@3.11 3.11.12_1`
- executable：`/opt/homebrew/bin/python3.11`
- venv：`/Users/sophon/Codex/WPF2React/.venv`
- venv Python：3.11.12 arm64
- 打包工具：pip 26.1.2、setuptools 83.0.0、wheel 0.47.0、packaging 26.2

复现命令：

```bash
cd /Users/sophon/Codex/WPF2React
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel packaging
.venv/bin/python -m pip install -r requirements-local.lock
.venv/bin/python -m pip check
```

依赖安装过程：

1. `requirements.txt` 在 Python 3.11/macOS arm64 上完整安装成功，未触发 Python 回退。
2. 下限解析最初选择了 lxml 6.1.1、sentence-transformers 5.6.0、openai 2.45.0；为贴近 `docs/DEPENDENCIES.md` 记录的原环境，明确恢复为 lxml 6.0.2、sentence-transformers 5.2.0、openai 2.4.0。
3. 首轮 `src.migration` 导入失败：`ModuleNotFoundError: No module named 'tiktoken'`。根因是当时 `requirements.txt` 只装 `autogen-ext==0.7.5`，未安装其 `openai` extra；现已改为 `autogen-ext[openai]==0.7.5`，干净安装会带入 aiofiles、tiktoken 及相关依赖。
4. 最终 `pip check`：`No broken requirements found`。完整已验证版本固化在 `requirements-local.lock`，声明缺口已同步修复到 `requirements.txt`。
5. 受执行沙箱限制，首次联网安装尝试出现代理/权限错误；在已授权的联网安装模式下重试成功。这不是包或 Python 兼容性失败。
6. pip 检查会提示用户级 `~/Library/Caches/pip` 在沙箱中不可写并禁用缓存；它不影响 `.venv` 安装、导入或 `pip check`，也没有为消除该提示而改变系统权限。

## 5. 真实入口与已确认架构

- 解析入口：`.venv/bin/python -m src.parser <project>`，实际调用 `src/parser/__main__.py:analyze_project`。
- 解析固定 7 步：C# → XAML/CSPROJ → C# 依赖 → 间接资源/数据/模板 → 页面依赖 → 静态资源 → 控件树。
- 关键解析产物：`outputs/<project>/dependency/page_dependency.json`、`cs_dependency.json`、`resource_dependency.json`、`data_resources.json`、`template_resources.json`、`indirect_resources.json` 和 `control_<page>.json`。
- 迁移入口：`.venv/bin/python -m src.migration <project>`，实际调用 `src/migration/__main__.py:migrate_project`。
- 迁移顺序：资源 → C# → 数据 → 页面；页面按依赖顺序迁移。
- `MigrationTeam` 在 autogen-core runtime 注册 7 类 Agent；页面控件树自底向上迁移，再由 `PageAssemblyAgent` 做 7 轮渐进组装。
- LLM 结构化输出使用原生 JSON mode、显式 JSON Schema、严格解析和最多一次同模型修复；不再使用响应标签。布局目标禁止生成 MUI `<Grid>`，使用 `<Box>`/`<Stack>`。
- 提示词固定目标 React 18.2.0、MUI 5.18.0、Emotion 11.11.x、TypeScript 5.9.3。
- 三档生成式模型通过 `.env` 配置：低档 `gpt-5.6-luna`、中档 `gpt-5.6-terra`、高档 `gpt-5.6-sol`；当前全部 Agent 只读取低档。AutoGen 0.7.5 对新名称所需的模型能力元数据由 `src/llm/client.py` 统一提供。

## 6. 实际验证结果

### 离线环境与导入

- `compileall -q src tests`：通过。
- `src.parser`、`src.llm`、`sentence_transformers`、`torch`、`src.migration`：补齐 OpenAI extra 后全部导入成功。
- 全部 `src` 和 `tests` 模块均能编译、导入。
- `.env` 已配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和低/中/高三档模型变量；只核对变量存在性与模型名，从未输出密钥或中转站地址。`.env` 被 Git 忽略且权限为 `0600`。
- `all-MiniLM-L6-v2` 已在组件 smoke 首次运行时下载到本机缓存，后续 MUI 语义选择成功加载。

### 解析

四个随仓库示例均通过真实 7 步入口，退出码均为 0：

| 示例 | C# 解析 | XAML/CSPROJ | 页面 | 控件树 | 结果 |
| ExpenseItDemo | 9 | 6 | 3 | 3 | 成功 |
| DataBindingDemo | 12 | 5 | 2 | 2 | 成功 |
| EditingExaminerDemo | 8 | 4 | 1 | 1 | 成功 |
| CustomComboBox | 7 | 4 | 1 | 1 | 成功 |

- 所有项目共生成 86 个 JSON，全部可被 `json.load` 解析。
- `ExpenseItDemo` 生成 24 个 JSON，关键 dependency/control 文件齐全。
- 页面顺序：`ViewChartWindow -> CreateExpenseReportDialogBox -> MainWindow`。
- C# 顺序：`EmailValidationrule -> NumberValidationrule -> LineItem -> LineItemCollection -> ExpenseReport`。
- 连续两次完整解析后的聚合 SHA-256 相同：`2f47bc888eaab5e5193b8bc4ae5a1405c83013dce89326344e16eafd6ec64f62`。
- 每次 `.venv/bin/python -m src.parser` 都出现非致命 `runpy` 警告，因为 `src/parser/__init__.py` 在执行包入口前导入了 `__main__`。本轮未修改。

### 现有测试

初始化阶段的领域测试目录按 `tests/parser/`、`tests/migration/`、`tests/llm/` 组织；公共基础设施统一后又补入与新源码包对应的 `tests/agents/`、`tests/common/`。2026-07-17 新增可重复的离线配置测试和仅使用合成输入的 LLM smoke。成功发起的生成式调用共 16 次，全部解析为 `gpt-5.6-luna`；未调用中、高档模型：

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `tests.parser.test_parser_pipeline` | 0 | 无；7 步解析及关键产物检查通过 |
| `tests.llm.test_model_config` | 0 | 三档配置正确，当前运行档为 low |
| `tests.llm.test_connectivity` | 0 | 单次 luna 响应非空且 smoke 内容正确 |
| `tests.migration.test_component_smoke` | 0 | Button 直接映射与组件生成成功 |
| `tests.migration.test_mui_select_smoke` | 0 | 合成自定义控件描述、语义选择和文档对齐成功 |
| `tests.migration.test_cs_smoke` | 0 | 合成 C# 迁移、分析和 TS 产物成功 |
| `tests.migration.test_data_smoke` | 0 | 单个合成 XAML 数据资源迁移成功 |
| `tests.migration.test_page_assembly_smoke` | 0 | 无资源/模板/数据时第 1/5/6/7 轮成功 |
| `tests.migration.test_page_pipeline_smoke` | 0 | 单控件 PageMigrate→PageAssembly，1/1 控件成功 |

所有合成测试产物写入系统临时目录并自动清理。用户随后明确确认仓库内容均为开源并批准通过已配置中转站进行真实测试，补测结果如下：

| 真实输入命令 | LLM 流水线 | 产物验证 |
| --- | --- | --- |
| `tests.migration.test_cs_migration` | 成功 | `LineItem.ts` 非空且结构正确 |
| `tests.migration.test_data_migration` | 3/3 数据资源成功 | `data.ts` 105 行，生成数据描述文件 |
| `tests.migration.test_single_page_migration` | 9/9 控件、6 个组装轮次成功 | 最终 TSX 静态验证通过 |

`ViewChartWindow` 实际执行了初始组装、资源修复、数据整合、布局优化、子页面集成和代码规范；模板轮因无模板依赖跳过。首次增强检查稳定复现了组件内部同名变量与未声明 `expenses`。根因是 `ensure_correct_export_name()` 把函数组件内部第一个局部 `const` 误当成组件声明。修复后，最终门禁还会检查精确 `{ open, onClose }` 合同、必需数据导入及使用、对象型数据不能直接调用数组方法；失败时仅允许一次带精确数据类型结构的定向修复，重试仍失败则整页迁移失败。当前 `ViewChartWindow.tsx` 使用 `expenseData.lineItems` 并通过门禁。

`MigrationTeam` 返回字典仍保留 `reasoning` / `mui_reasoning` 兼容键，但由于消息模型不提供该字段，当前值为空字符串。

### 迁移与前端

真实命令 `.venv/bin/python -m src.migration ExpenseItDemo` 的结果：

1. 资源阶段成功：`Watermark.png` 复制到 `results/ExpenseItDemo/public/Watermark.png`。
2. 源/目标 SHA-256 都是 `e864cf6204ae7ae3fb429a97d8bb85172cd3f1be6a38d73ef0fb94264eef3f4b`。
3. 该历史运行在当时因缺少 API key 停于 C# 阶段；当前 API 连通性、真实单文件 C#、真实数据以及真实单页面迁移均已进入 LLM 流程。
4. 七轮组装的最小条件路径和真实依赖条件路径均已验证；真实页面通过当前静态门禁。
5. 当前 `results/ExpenseItDemo` 包含资源和 `ViewChartWindow.tsx`，仍没有 `package.json`、lockfile、tsconfig 或 React 入口。因此未运行 `npm install`、build 或 start，也未安装任何目标项目 Node 依赖。
6. 包入口已改为按需导出，`python -m src.parser --help` 与 `python -m src.migration --help` 均按标准 CLI 退出且无 `runpy` 警告。

错误与运行证据位于 git-ignored 的 `logs/parser.log`、`logs/migration.log`、`logs/test_single_page_migration.log` 以及 `outputs/`、`results/`。

## 7. 当前阻塞与最小处理选项

1. **页面生成代码正确性**：已修复已知同名变量、未声明标识符、props 漂移、数据导入丢失和对象/数组误用，并在流水线内失败关闭；当前仍是轻量静态门禁，不替代完整 TypeScript 编译。
2. **语义模型**：`all-MiniLM-L6-v2` 已下载并验证；运行时仍会出现未配置 HF token 的限流提示，但本地加载和推理成功，不影响当前 smoke。
3. **完整迁移状态**：真实单文件、数据和单页面已测且通过；未继续消耗调用量运行整项目迁移，因此不能宣称真实项目完整迁移成功。
4. **React 工程骨架**：当前输出仍没有 `package.json`、tsconfig 或 React 入口，无法执行目标工程安装和构建。若后续完整迁移仍无这些文件，再决定补骨架还是按仓库既有预期提供模板。
5. **Windows/WPF 真值运行**：macOS 无法运行 WPF；且 ExpenseItDemo 缺外部项目引用。解析不受阻，但源应用编译/截图真值需要 Windows/.NET 10 环境和完整依赖。

## 8. 与研究稿的主要差异（只记录，不改造）

- 现代码保持两阶段“确定性解析 + LLM 多 Agent 迁移”；研究稿提出更细的 MigraUI 三阶段表达。
- 现代码保留硬编码 WPF 基础控件过滤、直接 MUI 映射/本地文档与可选语义相似度；研究稿提出更系统的标准映射、自定义控件摘要和多路检索。
- 现代码页面迁移是控件树自底向上、随后 7 轮页面组装；研究稿对直接子节点代码、跨页面集成和验证修复有不同实验化拆分。
- 研究稿的 RuleTrans-MUI、LLM-Direct-Budget、六个核心消融、结构/语义/视觉/成本指标与真实实验数据尚未在仓库中落地；文档中的 `[MOCK]` 数值不能当实验结果。
- 融合研究方案中的 C++ 代码复用项目与本仓库仅共享论文总目标和方法背景，不代表需要合并仓库或流水线。

## 9. 后续决定记录规则

后续每次改变 Python/Node 版本、依赖锁、入口、架构、模型、检索方式、测试状态或阻塞条件时，更新本文和 `AGENTS.md` 的简短状态。不要把密钥、企业数据、完整模型响应或敏感绝对路径写入可提交文档。

## 10. 结构整理记录

2026-07-16 至 2026-07-17 进行项目结构清理：

- `doc/` 改为更常见的 `docs/`。
- `DEPENDENCIES.md`、`GIT_WORKFLOW.md` 从根目录归档到 `docs/`；根目录当时保留 `README.md`、`AGENTS.md`、`CLAUDE.md` 等入口文档。2026-07-18 删除内容重复的 `CLAUDE.md`，后续统一以 `AGENTS.md` 作为开发契约入口。
- 迁移最终产物目录从 `result/` 改为 `results/`，与 `outputs/`、`logs/`、`tests/` 的复数目录风格一致；源码默认输出路径和测试/文档引用已同步。
- RAG 资料目录从 `rag/` 改为 `rags/`，默认检索路径与提示词引用已同步。
- 测试代码按 `src/` 包结构迁入 `tests/parser/`、`tests/migration/`、`tests/llm/`，删除根级重复运行器；新增不依赖 API 的解析流水线冒烟测试。
- 项目虚拟环境统一使用 `.venv/`；`src/` 和内部 Python 包名因属于生态与导入约定而保留标准名称。
- `.gitignore` 增补 Python/Node/缓存/日志/生成产物规则，同时显式放行根入口文档和 `docs/**/*.md`。

## 11. 两项目公共基础设施统一

2026-07-17 与 CodeIdiomMine 对齐了可复用工程底座；后续提示词改造仍保留 WPF 解析顺序、七类迁移 Agent、七轮页面组装和最终产物 schema：

- 新增 `src/common/` 与 `src/agents/base.py`，日志统一从 `src.common.logging` 导入，领域 Agent 仍通过 `src/migration/base.py` 继承。
- `src/llm/` 共享模块与 CodeIdiomMine 保持逐文件一致，集中模型分档、根 `.env`、模型元数据、JSON schema/修复和异步客户端关闭。
- `MigrationTeam` 改用 `register_agent` / `default_agent_id`，底层仍是相同的 AutoGen `register_factory` 与默认 key，消息类型和迁移流程未变。
- 日志从可能覆盖的脚本文件切换为追加写入的 `logs/<run-name>.log`；`src/logger.py` 仅保留兼容导入。
- 新增共享离线契约测试和 `scripts/check_shared_infrastructure.py`；统一规范记录在 `docs/guides/shared-development-conventions.md`。
- 当前 `pip check`、`src/tests/scripts` 编译、8 个共享离线测试、模型档位脚本、14 文件哈希对齐检查以及 7 个 Migration Agent 的 runtime factory 注册均通过；本轮提示词改造没有发起 LLM 请求、模型下载或完整迁移。

## 12. 分层评测实现基线

2026-07-18 在不改变两阶段迁移流程、Agent 数量、MUI 检索路径或七轮页面组装的前提下，新增只读 `src/migration/evaluation/`：

- 从 `control_*.json` 和 `page_dependency.json` 构建待人工核验的固定 GT 清单，组件单位为控件树实例；
- 组件判别器组合页面路径、文件名、符号、MUI/JSX 标签、名称和文本证据，并以 TypeScript 编译结果作最低可用性裁决；
- 页面入口单独编译，页面调用关系通过冻结 GT 边和预注册测试代码验证；迁移失败、测试未配置和评测环境错误分开记录；
- 人工登记原 WPF 与迁移后 React 的同页面、同状态截图对后，低档多模态模型按显式 JSON Schema 输出组件、布局、样式、内容忠实度和独立美观度；Overall Fidelity 由程序使用固定权重计算；
- 视觉调用沿用共享模型配置、中文结构化提示词、原生 JSON mode、严格完整响应解析和最多一次同模型修复。离线测试使用 Fake LLM，不下载模型、不发起付费调用；
- 指标定义、公式和适用边界记录在 `docs/EVALUATION_METRICS.md`，配置与 CLI 记录在 `docs/EVALUATION.md`。

本轮 `.venv/bin/python -m unittest discover -v` 共 24 个离线测试通过，其中视觉评测覆盖双图消息、固定权重、无效截图排除、缺图错误和单次 JSON 修复。未收到用户截图，因此尚未通过当前 OpenAI 兼容中转端点执行真实双图 smoke；官方模型能力不能替代该端到端验证。当前迁移结果仍缺 React 工程骨架，真实 TypeScript 编译指标暂不可用，此状态未被误计为迁移失败。
