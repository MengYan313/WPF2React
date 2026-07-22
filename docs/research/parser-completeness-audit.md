# 阶段一解析完整性两遍式审计

## 1. 范围与结论边界

本轮于 2026-07-23 从 `results/dataset/dataset-manifest.json` 动态选择状态为“保留”或“条件保留”的 20 个固定提交项目。第一遍先冻结现有解析器产物并完成全量审计，再按跨项目机制聚类实施通用修改；没有在审计中途按仓库名或固定路径增加规则。

本报告区分七阶段是否执行完成、文件与产物的一一对应、结构覆盖、语义引用覆盖和资源闭包。20/20 七阶段成功不等于绝对完整；候选仓库没有在 macOS 上构建或运行，缺少人工 GT 的字段语义也不能据此证明完全正确。本轮只进行静态读取和离线测试，没有执行候选仓库脚本、安装、测试或构建命令，也没有触发真实 LLM。

本地详细产物位于：

- 修改前解析产物：`outputs/parser-completeness/before/`；
- 修改后两次解析产物：`outputs/parser-completeness/after-run-1/`、`outputs/parser-completeness/after-run-2/`；
- 逐项目报告：`results/parser-completeness/{before,after-run-1,after-run-2}/projects/`；
- 聚合报告：`results/parser-completeness/{before,after-run-1,after-run-2}/completeness-report.md`；
- 分解析器解析率：各轮目录中的 `parser-rates.{json,md}`；
- 问题聚类：`results/parser-completeness/issue-clusters.{json,md}`；
- 前后对比：`results/parser-completeness/before-after-comparison.{json,md}`；
- unsupported/unresolved：各轮目录中的 `unsupported-unresolved.json`；
- 确定性证据：`results/parser-completeness/determinism.json`。

`repos/`、`outputs/` 和 `results/` 均为 Git 忽略的本地数据，研究文档不分发候选仓库源码。

## 2. 修改前全量审计

修改前 20 个项目均完成七阶段，但完整性审计发现七类跨项目问题：迁移控件树之外的视觉节点没有独立保留清单；Binding、Command、事件和资源标记只有原始字符串；C# 缺少 file-scoped namespace、record、字段式事件、多 declarator 和条件编译分支等结构；tree-sitter 恢复错误未进入产物诊断；partial 类型按简单名称估算会误合并；资源阶段仅有 29 条解析器链接；页面依赖只保留确定的 `new Page()` 边。

文件身份链本身没有发现回归：4780 个 C#/XAML/csproj 输入均有唯一 `repository-relative-posix-v1` ID、唯一镜像产物路径，缺失、重复与覆盖均为 0。该结论由跨目录同名 XAML、code-behind、业务 C# 和静态资源端到端夹具继续锁定。

## 3. 前后覆盖统计

| 指标 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 七阶段成功项目 | 20/20 | 20/20 |
| C#/XAML/csproj 输入与产物 | 4780/4780 | 4780/4780 |
| 缺失产物 / 重复 ID / 输出覆盖 | 0 / 0 / 0 | 0 / 0 / 0 |
| 原始 XML 元素 / 完整 XAML IR | 193863 / 193863 | 193863 / 193863 |
| 静默未分类 XAML 节点 | 0 | 0 |
| 页面视觉节点的迁移侧静默丢失 | 5815 | 0 |
| 迁移侧显式自定义控件清单 | 0 | 3391 |
| 结构化 Binding / Command / 事件 | 0 / 0 / 0 | 14815 / 2391 / 821 |
| 结构化 MultiBinding / PriorityBinding | 0 / 0 | 234 / 6 |
| 结构化 StaticResource / DynamicResource | 0 / 0 | 9662 / 10729 |
| C# 原始声明与 IR 的确定差额 | 1459 | 31 |
| 解析器已报告 ERROR / missing 节点 | 0 / 0 | 199 / 9 |
| 未报告的 tree-sitter 诊断 | 208 | 0 |
| 按完整类型名确认的 partial 组 / 文件 | 未可靠区分 | 19 / 47 |
| C# 确定依赖边 / 源码证据 | 9663 / 0 | 7319 / 8032 |
| 解析器资源 source ID | 605 | 1015 |
| 解析器显式资源引用记录 | 29 | 21043 |
| 解析器已解析资源引用 | 0 | 8257 |
| 解析器未解释资源引用 | 0 | 0 |
| 页面确定边 / 确定边证据 / 候选边 | 119 / 0 / 0 | 119 / 119 / 140 |
| 页面暂不支持引用 | 0 | 29 |

修改后的 31 个 C# 声明差额全部集中在三个已报告恢复错误的文件：LLPlayer 的 `SubtitlesExportDialogVM.cs`、Playnite 的 `LiteDBFileReaderV7.cs` 和 1Remote 的 `SessionControlService.cs`。无 tree-sitter ERROR/missing 的文件没有剩余确定声明差额。

总 unresolved 从 2050 增至 2686，不表示解析退化：新增的 831 条 C# 候选依赖、140 条页面候选边和 29 条页面暂不支持引用以前大多被静默忽略，现在保留源码证据与置信级别。详细分类必须结合 `unsupported-unresolved.json` 阅读。

### 3.1 分解析器解析率与 90% 验收

解析率衡量“应处理单位是否已有产物、结构化结果、源码证据或显式 unsupported/unresolved 分类”，不是人工 GT 下的语义正确率。显式记录暂不支持或无法唯一确定的内容计为已处理，因为它已经避免静默丢失；它仍不能被表述为可直接迁移或语义正确。

总体采用七个解析器的等权宏平均，跨项目聚合后的七个解析器还必须分别达到 90%（含）才判定通过。该口径避免 C#/XAML 大量节点掩盖页面或资源阶段的小分母问题。

| 解析器 | 修改前 | 修改后 | 修改后已处理/应处理 | 结论 |
| --- | ---: | ---: | ---: | --- |
| C# 结构解析器 | 97.21% | 99.95% | 59665/59696 | 通过 |
| XAML/csproj 解析器 | 83.09% | 100.00% | 234945/234945 | 通过 |
| C# 依赖解析器 | 2.18% | 100.00% | 8170/8170 | 通过 |
| 间接资源解析器 | 100.00% | 100.00% | 60/60 | 通过 |
| 页面依赖解析器 | 73.48% | 97.92% | 1034/1056 | 通过 |
| 静态资源解析器 | 2.92% | 99.96% | 21590/21598 | 通过 |
| 控件依赖解析器 | 74.24% | 99.96% | 22601/22609 | 通过 |
| **七解析器宏平均** | **61.87%** | **99.68%** | — | **通过** |

20 个项目各自的七解析器宏平均均高于 90%，最低为 Prism 的 95.70%。若进一步要求“单项目内每个解析器也分别达到 90%”，则有 16/20 通过；4 个局部低样本项为 MvvmCross 静态资源 6/7（85.71%）、Prism 页面依赖 11/14（78.57%）、Accelerider.Windows 页面依赖 55/68（80.88%）和 snoopwpf 静态资源 8/10（80.00%）。本轮验收以跨项目分解析器聚合口径为准，因此这些项目不阻塞 90% 门槛，但作为可复现的后续优化清单保留；按当前任务范围不再追加解析规则。

## 4. 解析器修改记录

### 4.1 仓库相对路径 ID 全链路

- 动机：避免跨目录同名文件覆盖、错误页面调度和评测 basename 猜测。
- 影响范围：全体项目；修改前审计未发现新碰撞，作为 P1 防回归契约保留。
- 最小复现：`tests/fixtures/parser/duplicate-paths/` 中两套 `MainWindow.xaml`、code-behind、`Shared.cs` 和 `logo.svg`。
- 前后结果：历史扁平身份会冲突；当前夹具的源码、解析 JSON、C# 与页面节点、控件树、TSX 目标和评测 manifest 均使用唯一镜像路径，评测器只按精确相对路径匹配。
- 测试：`RelativePathIdentityTests` 与 `tests.migration.test_evaluation`。
- 限制：组件符号仍可由路径派生，但不能反向承担文件身份。

### 4.2 XAML 完整节点清单与语义引用

- 动机：19 个项目存在 5815 个迁移侧未保留视觉节点，20 个项目的 Binding、Command、事件和资源表达式缺少稳定结构。
- 影响范围：节点清单影响 19 个项目，语义引用影响全部 20 个项目。
- 最小复现：合成窗口同时包含自定义控件、附加/命名空间属性、Binding、MultiBinding、PriorityBinding、Command、事件和合并资源字典。
- 前后结果：旧 `controls` 保持兼容；新增完整 `node_inventory`、分类原因、节点路径、源码行、原始属性和 `semantic_references`，迁移侧静默视觉节点丢失由 5815 降为 0。
- 测试：`XamlSemanticTests` 包含正例、字面量/转换器负例和两次序列化确定性比较。
- 限制：1042 个节点仍明确标为 unsupported；复杂标记扩展保留原值，不伪装成已理解语义。

### 4.3 C# 声明覆盖与恢复诊断

- 动机：17 个项目存在确定声明差额，10 个项目有 tree-sitter ERROR/missing 但旧产物未报告。
- 影响范围：file-scoped namespace、record、事件字段、多 declarator、泛型与条件编译分支是通用 C# 结构；条件编译实测影响 Accelerider.Windows、Playnite、EarTrumpet、1Remote、ILSpy。
- 最小复现：file-scoped namespace 下的泛型 partial record、多个字段与事件、错误恢复源码，以及 `#if/#else` 中的字段和方法。
- 前后结果：声明差额由 1459 降为 31；199 个 ERROR 与 9 个 missing 全部写入诊断；条件编译两侧均保留并记录指令上下文，不在 macOS 上猜测编译符号。
- 测试：`CsStructureCompletenessTests` 覆盖正例、恢复错误、条件编译和确定性；14 个无语法错误的真实最小复现文件差额为 0。
- 限制：剩余 31 个差额位于三个恢复错误文件，只报告部分解析，不修改不可信输入源码。

### 4.4 C# partial 与歧义依赖

- 动机：按简单类型名关联会把不同 namespace 的同名类型误连，旧 partial 统计也会把普通重复类型误认为 partial。
- 影响范围：修改前简单名估算波及全部 20 个项目；修改后确认 19 个完整类型名 partial 组、47 个文件。
- 最小复现：`A.Shared`、`B.Shared`、未限定 `Shared` 消费者和两个 `Demo.Combined` partial 文件。
- 前后结果：不再向所有同名候选建立确定边；无法消歧的引用进入 `candidate_dependencies`/`unresolved_references`，partial 按 qualified name 分组。7319 条确定依赖边具有 8032 条逐符号源码证据，证据数可因同一目标文件对应多个符号而大于边数。
- 测试：`CsDependencyTests` 同时包含候选正例、`Sharedness` 负例、循环依赖与重复运行确定性。
- 限制：缺少语义编译环境时，别名、条件编译和复杂泛型可能仍只能形成候选边。

### 4.5 资源闭包与缺失 csproj 后备

- 动机：19 个项目的仓库资源、项目声明和 XAML 引用不闭合；缺少 csproj 时合法空结果会掩盖真实图片与字体。
- 影响范围：全量资源 source ID 从 605 增至 1015；关键回归 Page-Navigation-using-MVVM 虽不在 20 个实验项目中，仍用于验证通用后备。
- 最小复现：`tests/fixtures/parser/missing-csproj/` 包含合并字典、图片、字体和缺失目标；另有多 csproj 夹具。
- 前后结果：项目声明、XAML 引用和仓库扫描合并；引用被分类为声明文件、仓库内未声明文件、内部键、动态、外部、缺失或暂不支持。Page-Navigation 回归得到 18 个资源、52/52 条已解析引用和 0 条未解释引用。
- 测试：`ResourceDependencyTests` 覆盖缺失/多 csproj、正例、缺失目标和两次运行确定性。
- 限制：仓库扫描发现不等于项目构建会打包该文件，因此保留 `declared_in_project` 与 `discovery_sources`。

### 4.6 页面和框架导航候选

- 动机：16 个项目含 MVVM、DataTemplate、Prism、MvvmCross、DI、Command 或字符串路由证据，不能只审计 `new Page()`。
- 影响范围：保留原 119 条确定边，新增 140 条解析器候选边和 29 条暂不支持引用。
- 最小复现：合成 Shell/Detail 页面含 `new DetailView()`、DataTemplate、MvvmCross `Navigate`、Prism `RequestNavigate`、Command 导航及 `NavigateCount` 负例。
- 前后结果：每条确定边和候选边均保存机制或解析方式、source ID、目标 ID、行号、证据和置信度；119 条确定边具有 119 条证据，不把不唯一目标升级为确定边。
- 测试：`PageDependencyCandidateTests` 覆盖正例、负例和重复运行确定性。
- 限制：框架容器、反射和运行时字符串路由没有静态 GT，必须保留为候选或 unsupported。

### 4.7 可重复审计与确定性比较

- 动机：七阶段成功无法衡量文件、结构、语义和资源闭包。
- 最小复现：同名路径夹具与两个仅输出根不同的临时运行目录。
- 前后结果：新增统一运行、完整性审计、分解析器解析率、问题聚类/前后统计和逐文件确定性比较脚本。最终两次运行各产生 5654 个结构化 JSON，5654/5654 语义哈希一致；两轮各 25 个统计/逐项目报告，25/25 一致。
- 测试：`ParserCompletenessAuditTests` 覆盖闭包、重复审计、根路径归一化及 90% 含边界；数组顺序改变会使比较失败。
- 限制：只归一化明确记录的输出根路径，运行耗时和运行摘要不参与语义哈希。

全部修改后的统一全量回归结果均为：20/20 项目七阶段成功、4780/4780 输入一一对应、0 输出覆盖、两次解析产物和统计报告完全一致。

## 5. 剩余限制

- 10 个项目仍含 199 个 tree-sitter ERROR 和 9 个 missing 节点；它们现在有源码范围和证据，但不等于已修复语法版本或条件编译环境。
- 1042 个 XAML 节点为显式 unsupported，41 条资源引用目标不存在，278 条属于外部或程序集资源，12380 条属于动态或暂不支持引用；这些都不是静默成功。
- Playnite 仍有 2 条 `MainWindow` 短名引用无法静态唯一解析，保持歧义记录。
- macOS 环境没有执行 WPF 构建、Windows 运行时导航、资源打包或 UI 行为验证。
- 本轮项目既用于发现问题又用于回归，结果不能表述为对未知仓库的泛化能力。

## 6. 复现命令

```bash
# 修改前产物已冻结时重新生成同版审计报告
.venv/bin/python scripts/audit_parser_completeness.py \
  --parse-root outputs/parser-completeness/before \
  --report-root results/parser-completeness/before

# 最终解析完整运行两次
.venv/bin/python scripts/run_parser_completeness.py \
  --output-base-dir outputs/parser-completeness/after-run-1
.venv/bin/python scripts/run_parser_completeness.py \
  --output-base-dir outputs/parser-completeness/after-run-2

# 两轮逐项目审计
.venv/bin/python scripts/audit_parser_completeness.py \
  --parse-root outputs/parser-completeness/after-run-1 \
  --report-root results/parser-completeness/after-run-1 \
  --enforce-rate-threshold
.venv/bin/python scripts/audit_parser_completeness.py \
  --parse-root outputs/parser-completeness/after-run-2 \
  --report-root results/parser-completeness/after-run-2 \
  --enforce-rate-threshold

# 问题聚类、前后对比与解析/报告确定性
.venv/bin/python scripts/summarize_parser_completeness.py \
  --before-root results/parser-completeness/before \
  --after-root results/parser-completeness/after-run-1 \
  --output-root results/parser-completeness
.venv/bin/python scripts/compare_parser_completeness_runs.py

# 60 个相关离线 unittest；占位配置只供不发请求的契约测试构造客户端
OPENAI_API_KEY=offline-test-placeholder \
OPENAI_BASE_URL=http://127.0.0.1:9 \
.venv/bin/python -m unittest \
  tests.parser.test_dataset_parser_regressions \
  tests.parser.test_parser_completeness_audit \
  tests.common.test_shared_infrastructure \
  tests.migration.test_evaluation \
  tests.migration.test_baselines \
  tests.migration.test_page_validation \
  tests.migration.test_prompt_contracts \
  tests.migration.test_visual_evaluation -v
.venv/bin/python -m tests.parser.test_parser_pipeline
.venv/bin/python -m tests.llm.test_model_config
```
