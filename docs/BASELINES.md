# UI 迁移 Baseline 设计与运行规范

- 文档版本：1.0
- 适用项目版本：W2MR 4.4
- 方法标识：`RuleTrans-MUI`、`LLM-Direct-Budget`、`MigraUI-NoRAG`
- 相关实现：`src/migration/baselines/`

本文详细定义三条 WPF→React/MUI 实验 baseline 的研究角色、输入边界、算法流程、预算、产物、验证方式和公平性约束。完整 `MigraUI` 是待比较的本方法，不计入 baseline；`MigraUI-NoRAG` 同时承担第三条 baseline 和 RAG 核心消融两个角色。

## 1. 研究定位

三条 baseline 分别提供确定性规则下界、绕过结构化 Pipeline 的纯 LLM 对照，以及只去掉目标组件知识的本方法消融。它们回答的不是同一个局部问题，而是从三个方向限定完整方法的收益来源。

| 方法 | 方法类别 | 主要研究问题 | 运行重复 |
| --- | --- | --- | --- |
| `RuleTrans-MUI` | 传统规则适配基线 | 固定解析、映射和模板在没有学习能力时能完成多少迁移？ | 确定性运行一次 |
| `LLM-Direct-Budget` | 预算匹配纯 LLM 基线 | 不构造 IR、不拆组件、不使用 RAG 时，基础模型本身能完成多少迁移？ | 预注册种子至少三次 |
| `MigraUI-NoRAG` | 消融 baseline | 保留结构化流程和修复，仅移除 MUI 知识检索后性能如何变化？ | 与完整方法相同种子至少三次 |
| `MigraUI` | 完整方法，不属于 baseline | 结构、RAG、自底向上组装和有界修复共同作用时的整体效果如何？ | 与生成式 baseline 配对运行 |

`LLM-Direct-Full` 只作为可选成本敏感性分析，不替代预算匹配的 Direct baseline，也不进入三条 baseline 的正式主比较口径。

## 2. 公共公平性契约

### 2.1 相同目标环境

三种方法共享由代码生成的空白 Vite 工程骨架：

| 依赖 | 固定版本 |
| --- | --- |
| React / React DOM | 18.2.0 |
| MUI / MUI Icons | 5.18.0 |
| Emotion React / Styled | 11.11.4 / 11.11.5 |
| TypeScript | 5.9.3 |
| React Router | 6.28.0 |
| Vite | 5.4.21 |
| Vitest | 2.1.8 |

骨架只包含 `package.json`、`tsconfig.json`、Vite 配置、HTML 入口、React 入口和空 `App.tsx`，不包含目标页面、路由、迁移提示或参考实现。二进制图片和字体按源项目相对路径复制到 `public/`；代码引用如何恢复仍由各方法自己负责。

### 2.2 运行隔离

每个方法—运行—项目组合使用不可覆盖的独立目录：

```text
results/baselines/<method-id>/<run-id>/<project-id>/
outputs/baselines/<method-id>/<run-id>/<project-id>/
```

前者是可构建的目标工程，后者是运行清单、中间产物和审计记录。若目录已存在且非空，程序拒绝覆盖并要求新的 `run-id`。这样可以防止不同方法、不同种子或失败重跑之间互相读取旧代码。

### 2.3 隐藏评测

三种方法都不得读取 evaluation manifest、测试断言、源 WPF 截图对应的目标截图、人工标签或参考 React 实现。统一评测器只读目标工程，不执行自动修复、路由补写、组件替换或依赖恢复。

### 2.4 公共写入安全

模型生成文件只允许使用目标工程内的相对 `.ts`、`.tsx` 和 `.css` 路径。绝对路径、`..`、`node_modules` 和其他后缀会被拒绝；同一响应中的全部文件先完成路径、重复项和非空校验，再统一写入，避免半批次落盘。

## 3. RuleTrans-MUI

### 3.1 定义与输入

`RuleTrans-MUI` 是传统“解析—固定映射—模板生成”范式在 WPF→React/MUI 上的适配实现。它读取原始 XAML；同名 C# 仅用于恢复能够通过静态模式明确判定的窗口打开和关闭行为，不解释任意业务语义。

该方法明确不使用 LLM、Embedding、RAG、Agent、语义摘要、Parser 阶段 IR 或学习式修复，因此输出对相同源码和规则版本是确定的。

### 3.2 处理流程

1. 递归发现 `Window`、`Page`、`UserControl` 和 `NavigationWindow` 页面根节点。
2. 使用关闭实体解析和网络访问的 XML 解析器读取 XAML；优先使用 lxml，缺失时回退 ElementTree。
3. 按固定控件和布局规则自顶向下生成 TSX，并保留可观察名称、文本、尺寸、网格位置、Binding、Style 和事件证据。
4. 扫描同名 code-behind 中与 XAML `Click`/`Command` 直接关联的方法；仅恢复 `new TargetWindow` 加 `Show/ShowDialog` 和 `Close/DialogResult` 这两类明确模式。
5. 为可判定的子窗口生成 `useState`、`open/onClose` 和 Dialog 引用；为入口页生成 `App.tsx` 挂载。
6. 无规则的自定义控件输出带 `data-unsupported-wpf` 的显式 placeholder，并写入逐页面审计记录。

页面文件成功生成不代表所有控件成功迁移。存在 placeholder 时，页面生成状态仍可为 `success`，但 `unsupported_control_count` 和逐控件记录会保留失败事实；正式 CIRR/C-CPR 等固定分母指标负责把对应控件计为未复刻，而不是缩小分母。

### 3.3 主要映射规则

| WPF 结构或控件 | React/MUI 输出 | 关键规则 |
| --- | --- | --- |
| `Grid` | `Box` | 使用 CSS Grid；禁止生成 MUI `<Grid>` |
| `StackPanel`、`ToolBar`、`WrapPanel` | `Stack` | 根据 Orientation 或控件类型设置方向 |
| `Border`、`DockPanel`、`Canvas`、`ScrollViewer` | `Box` | 保留尺寸、Margin 和网格位置证据 |
| `Button` | `Button` | 保留文本、事件名；可判定时恢复窗口打开/关闭 |
| `TextBox`、`PasswordBox` | `TextField` | 保留 Binding、multiline、password 等属性 |
| `ComboBox` | `Select` + `MenuItem` | 保留 ItemsSource/SelectedValue 证据 |
| `CheckBox`、`RadioButton` | `FormControlLabel` + 对应控件 | 保留 label 和禁用状态 |
| `ListBox`、`ListView` | `List` / `ListItem` | 保留可访问名称和数据绑定证据 |
| `DataGrid` | MUI Table 组件族 | 从显式列抽取表头；无列时生成占位表头 |
| `Menu`、`MenuItem` | MUI Menu 组件族 | 保留 Header、Command 和可判定事件 |
| `Image` | `Box component="img"` | 显式 Source 映射到 `public/`；无法解析时记录 unresolved source |
| 未知命名空间控件 | `Box` placeholder | 记录源标签与稳定节点路径，不调用其他方法补齐 |

规则实现版本记录为 `ruletrans-mui-v1`。规则表、导航模式或模板行为发生实验语义变化时必须增加该版本，不能在同一正式实验配置内静默修改。

### 3.4 能力边界

- 不解释任意 C# 业务逻辑、反射、动态资源键、复杂 RoutedEvent 或 ViewModel 状态机。
- Style/Template 主要以证据属性保留，不尝试模拟完整 WPF 样式系统。
- 不能用 MigraUI 的组件检索、页面依赖 IR 或 LLM 修复未知控件。
- placeholder 是可追踪失败，不是等价实现。

## 4. LLM-Direct-Budget

### 4.1 定义与输入

`LLM-Direct-Budget` 只给基础模型提供机械整理的原始材料：

- 当前页面 XAML；
- 同名 C# 优先、随后按稳定路径顺序加入同目录 C#；
- 项目文件相对路径清单；
- 固定目标框架、页面组件模式和 JSON 输出 Schema。

它不读取 `outputs/<project>/` 中的 Layout/Data/Dependency IR，不建立组件树或页面依赖图，不查询 MUI 文档，不使用规则映射、多 Agent、自底向上顺序或编译反馈修复。

### 4.2 机械分包

每个非 `App.xaml`、非 `Styles.xaml` 页面形成一个页面包。同名 code-behind 始终优先保留；当输入超过单次上限时，只从稳定排序末尾移除非同名 C#，并把省略文件写入 `package_manifest.json`。如果页面和同名 C# 本身已经超过上限，运行直接失败，不做语义摘要或 IR 压缩。

所有页面包独立生成。正式默认配置在两个以上页面成功后允许一次工程级合并调用，用于更新 `App.tsx` 或明显不一致的页面接口；合并仍只能读取原文件路径清单和已生成源码，不能引入 Parser IR。

### 4.3 预算模型

默认总预算为 120000 tokens，单次输入上限为 24000，单次输出上限为 8000。每个结构化任务可能因 JSON 校验失败使用同一模型修复一次，因此预算账本按最坏情况预留：

```text
reserved(task) = 2 × (estimated_input_tokens + allowed_output_tokens)
```

离线估算器为保证无下载、可确定复现，对 CJK 字符按一个 token、其他字符按四分之一个 token 估算，并以 UTF-8 字节数除以四作为另一条下界。该估算只用于调用前预算门禁；正式成本以 AutoGen/provider 返回的实际 prompt/completion usage 为准。

预算是上限，不要求为耗尽预算而制造额外调用。`provider_call_upper_bound` 记录最坏调用次数，`provider_actual_calls` 和 provider token 字段记录真实运行值。

### 4.4 结构化生成与失败关闭

模型只返回以下逻辑结构：

```json
{
  "files": [
    {"path": "MainWindow.tsx", "content": "完整源码"}
  ],
  "unresolved_items": []
}
```

响应使用共享 `build_json_system_prompt(...)`、原生 JSON mode、显式 JSON Schema、完整响应解析和最多一次同模型 JSON 修复。页面响应还必须满足：

- 恰好存在一个同名 `<page>.tsx`；
- 声明同名 function 并 default export；
- `MainWindow` 不接收 props；其他 Window/Dialog 只接收 `{ open, onClose }`；
- 不包含 MUI `<Grid>`；
- 所有返回文件路径与内容通过原子式预检。

静态门禁只决定本次输出是否可作为该方法产物，不把错误反馈给模型进行第二轮代码修复，因此不构成本文方法的工具反馈闭环。

### 4.5 审计信息

Direct 记录机械分包清单、prompt/schema 哈希、模型名、逻辑调用、实际 provider 调用、估算与实际 token、最大预算、未解决事项、生成文件哈希和失败原因。审计日志不保存完整 prompt、响应或密钥。

## 5. MigraUI-NoRAG

### 5.1 定义

`MigraUI-NoRAG` 是完整迁移流程的单变量消融：只关闭 MUI 知识库查询、语义相似度和文档注入，其余现有 MigraUI 行为保持不变。它不是“Direct 加 Parser”，也不是把所有 MUI 信息清空的随机退化版本。

### 5.2 与完整方法的差异

| 机制 | MigraUI | MigraUI-NoRAG |
| --- | --- | --- |
| Parser 阶段1产物 | 保留 | 保留并复制到本次隔离目录 |
| 标准 WPF→MUI 名称映射 | 启用 | 启用，仅返回组件名称 |
| 映射中的 usage/notes | 注入 | 不读取到生成上下文，返回空文档 |
| 未知控件功能描述 LLM | 可用 | 禁用 |
| sentence-transformers/OpenAI Embedding | 可用 | 禁用且不加载模型 |
| MUI 组件索引和候选检索 | 启用 | 禁用 |
| 组件拆分 | 保留 | 保留 |
| 自底向上迁移 | 保留 | 保留 |
| 直接子节点代码注入 | 保留 | 保留 |
| 页面依赖调度 | 保留 | 保留 |
| 适用的多轮页面组装 | 保留 | 保留 |
| 最终静态验证和有界修复 | 保留 | 保留 |

标准映射保留是为了只消融“检索知识与文档上下文”，避免同时改变组件名称先验。未知控件返回空候选和空文档，由生成模型仅依据 WPF 源码与固定目标版本处理。

### 5.3 隔离执行流程

1. 创建本次独立目标骨架和资源副本。
2. 从同一 Parser 结果只复制 `cs/`、`xaml/` 和 `dependency/` 到 `artifact_root/parser/<project>`。
3. 不复制旧 `migration/` 目录，防止读取其他方法或旧运行的中间结果。
4. 使用 `enable_mui_retrieval=False` 启动原 `MigrationOrchestrator`。
5. 正式运行资源、C#、数据和全部页面阶段；页面仍按依赖图顺序迁移。
6. 汇总迁移结果以及所有 Runtime Agent 的逻辑调用、真实 provider 调用和实际输入/输出 token。

`--page` 与 `--skip-project-stages` 只服务低成本合成 smoke。正式实验不得使用这两个选项缩小输入或跳过阶段。

## 6. 产物说明

### 6.1 公共产物

| 路径 | 内容 |
| --- | --- |
| `results/.../package.json` | 固定目标依赖和构建命令 |
| `results/.../tsconfig.json` | 固定 TypeScript 编译配置 |
| `results/.../App.tsx`、`main.tsx` | 空入口或由方法生成的入口 |
| `results/.../<page>.tsx` | 目标页面代码 |
| `results/.../public/` | 二进制资源副本 |
| `outputs/.../run_manifest.json` | 方法、版本、状态、路径、时间和成本摘要 |

### 6.2 方法专属产物

| 方法 | 产物 | 作用 |
| --- | --- | --- |
| RuleTrans | `generation_records.jsonl` | 页面源码/目标哈希、节点数、未知控件和导航目标 |
| Direct | `package_manifest.json` | 每个机械包的包含、省略文件和稳定规则 |
| Direct | `generation_records.jsonl` | 页面与可选 merge 的状态、文件哈希和 unresolved items |
| Direct | `llm_call_records.jsonl` | task、模型、prompt/schema 哈希、估算 token 和耗时 |
| NoRAG | `parser/<project>/` | 本次隔离的阶段1副本与新迁移中间结果 |
| NoRAG | `migration_summary.json` | 原编排器的页面级成功/失败结果 |

所有 JSON/JSONL 审计文件都不包含密钥。研究数据发布前仍应检查源文件路径和 unresolved 文本是否涉及不能公开的信息。

## 7. 运行命令

### 7.1 前置 Parser

NoRAG 需要阶段1产物；正式实验应先对冻结源码运行 Parser：

```bash
.venv/bin/python -m src.parser ExpenseItDemo
```

RuleTrans 和 Direct 只读取 `repos/` 原始项目，不读取该 Parser 输出。

### 7.2 正式配置示例

```bash
.venv/bin/python -m src.migration.baselines RuleTrans-MUI ExpenseItDemo \
  --run-id rules-v1

.venv/bin/python -m src.migration.baselines LLM-Direct-Budget ExpenseItDemo \
  --run-id direct-seed-1 \
  --total-token-budget 120000 \
  --max-input-tokens-per-call 24000 \
  --max-output-tokens-per-call 8000

.venv/bin/python -m src.migration.baselines MigraUI-NoRAG ExpenseItDemo \
  --run-id no-rag-seed-1
```

### 7.3 CLI 选项

| 选项 | 适用方法 | 含义 |
| --- | --- | --- |
| `--run-id` | 全部 | 必填且不可复用的运行标识 |
| `--source-base-dir` | 全部 | 原始项目根目录，默认 `repos` |
| `--result-base-dir` | 全部 | 目标工程根目录，默认 `results/baselines` |
| `--artifact-base-dir` | 全部 | 审计产物根目录，默认 `outputs/baselines` |
| `--parser-output-base-dir` | NoRAG | Parser 输出根目录，默认 `outputs` |
| `--page` | Direct / NoRAG smoke | 只运行指定页面，可重复；正式实验禁用 |
| `--no-merge` | Direct smoke | 关闭可选工程合并；正式配置按预注册值运行 |
| `--skip-project-stages` | NoRAG smoke | 跳过资源/C#/数据阶段；正式实验禁用 |
| token 三个预算选项 | Direct | 总预算、单次输入上限和单次输出上限 |

## 8. 验证与当前证据

### 8.1 离线测试

```bash
.venv/bin/python -m unittest tests.migration.test_baselines -v
.venv/bin/python -m unittest discover -v
```

baseline 离线测试覆盖：目录隔离、防覆盖、原子文件写入、RuleTrans 确定性、未知控件、Dialog 打开/关闭、Direct 机械包和预算、可选 merge 计数、NoRAG 文档隔离、旧中间产物排除，以及 JSON 修复的 provider 调用统计。

### 8.2 真实 LLM smoke

```bash
.venv/bin/python -m tests.migration.test_llm_direct_baseline_smoke
.venv/bin/python -m tests.migration.test_no_rag_baseline_smoke
```

W2MR 4.4 实现验证使用合成、非敏感输入：

| 方法 | smoke 范围 | 结果 |
| --- | --- | --- |
| Direct | 单个 `MainWindow` 页面、关闭 merge | 成功；1 个逻辑/provider 调用，2641 实际 tokens |
| NoRAG | 单 Button 页面、跳过项目级阶段 | 成功；6 个 provider 调用，12079 实际 tokens；检索关闭 |

token 数只记录本次 smoke 的实际证据，不是正式实验均值，也不用于方法优劣结论。

### 8.3 目标构建

```bash
cd results/baselines/RuleTrans-MUI/rules-v1/ExpenseItDemo
npm install
npm run build
```

同一构建步骤适用于另外两种方法。W2MR 4.4 验证中，RuleTrans 对四个本地输入共生成 7/7 页面，四个目标工程的 `tsc --noEmit && vite build` 均通过。安装锁定依赖时 npm 报告 8 个已知依赖漏洞；为保持研究版本不变，没有执行会升级依赖的 `npm audit fix --force`。

### 8.4 只读评测接入

```bash
.venv/bin/python -m src.migration.evaluation build-manifest ExpenseItDemo \
  --target-root results/baselines/RuleTrans-MUI/rules-v1/ExpenseItDemo \
  --output outputs/evaluation/manifests/ExpenseItDemo.json

.venv/bin/python -m src.migration.evaluation run \
  outputs/evaluation/manifests/ExpenseItDemo.json \
  --method-id RuleTrans-MUI \
  --run-id rules-v1 \
  --workspace-root . \
  --output-dir outputs/evaluation/RuleTrans-MUI/rules-v1/ExpenseItDemo
```

实现 smoke 的未核验 manifest 在 ExpenseItDemo 上得到 C-CPR=0.8226、P-CPR=1.0。该数字只证明 baseline 输出能够接入当前评测器；manifest 仍是 `unreviewed`，调用边测试也未冻结，因此不能写入论文正式结果。

## 9. 正式实验检查清单

1. 冻结源项目 commit、项目清单和开发/验证/测试划分。
2. 对同一源码运行确定性 Parser，并记录阶段1产物哈希。
3. 独立核验并冻结 evaluation manifest；禁止把它放入方法上下文。
4. 固定 W2MR 版本、三条方法内部版本、模型名、温度、预算、种子和依赖锁。
5. RuleTrans 运行一次；Direct、NoRAG 和完整 MigraUI 使用相同预注册种子配对运行至少三次。
6. 每次使用新 `run-id`，保留完整 run/package/call manifest 和失败记录，不只保留最佳结果。
7. 在每个目标目录安装同一锁定依赖，执行同一 Build/Contract/Navigation/Screenshot 评测。
8. 报告固定分母、失败类别、均值、方差、置信区间、provider tokens、API 金额和墙钟时间。
9. 把不适用指标记为“不适用”，不能填 0；条件视觉分数必须与截图覆盖率共同解释。

当前 smoke 已验证实现入口和最小链路，但没有完成冻结清单上的三种 baseline 全项目重复实验。正式结果必须由上述流程重新生成，不能复用 smoke 数字。
