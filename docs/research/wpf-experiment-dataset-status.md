# WPF 实验数据集现状统计

数据冻结时间：2026-07-24T11:29:46.364375+00:00。

本文由结构化清单和统计脚本生成，所有数值均来自固定提交与本地解析摘要。

## 0. 权限与环境预检

| 项目 | 结果 |
| --- | --- |
| Git | 可用 |
| GitHub CLI | 未安装；非阻塞，改用 Git 与公开 GitHub REST API |
| GitHub SSH | 成功 |
| GitHub API | 未认证 core API 60 次/小时；使用本地缓存，最终元数据错误 0 |
| 网络与公开克隆 | 成功 |
| 启动时磁盘空间 | 约 37 GiB |
| Python | .venv/bin/python，Python 3.11 |
| 解析冒烟 | ExpenseItDemo 七阶段通过 |
| 候选源码执行 | 未执行候选仓库脚本、构建、测试或安装命令 |
| 阻塞性权限问题 | 无 |

## 1. 候选与筛选结果

| 指标 | 数量 |
| --- | --- |
| 候选总数 | 26 |
| PDF 原始候选 | 22 |
| GitHub 补充候选 | 4 |
| PDF 星标候选 | 9 |
| 最终纳入（保留 + 条件保留） | 20 |

| 状态 | 数量 |
| --- | --- |
| 保留 | 6 |
| 条件保留 | 14 |
| 淘汰 | 6 |

### 1.1 选取方法与合理性

候选筛选采用“硬约束排除、软证据排序、覆盖增量复核”的三步方法，不以 Star、活跃度或解析成功率中的任一单项替代质量判断。

硬约束要求候选具有可确认的 WPF/XAML + C# 源码、明确可用的开源许可证、可固定的 commit 和目标路径，以及足以复现工程结构的 `.csproj` 等项目定义。缺少许可证、缺少工程定义、源技术栈不属于 WPF，或源码无法按固定提交重建时直接淘汰。

通过硬约束后，使用以下软证据判断保留价值：

- 场景与领域是否补充已有项目，而非重复增加同类小样例；
- 页面规模、MVVM/框架模式、自定义控件、资源和导航机制是否形成难度梯度；
- 官方背景、社区采用、提交历史和近期活跃度是否提供额外质量证据；
- 许可证义务、历史版本、平台绑定和外部服务是否可以被明确记录并在实验中隔离。

解析七阶段成功只是纳入后的最低可处理性检查，不等同于源码质量、可构建性或迁移正确性。复杂项目不会仅因难迁移而被淘汰，而是进入压力集或平台专项；单页样例、框架 Playground 和 Gallery 也不会与完整业务应用混算一个主指标。

当前 20 个正式项目曾用于发现并修复解析器问题，因此适合方法开发和分层评测，但不能单独证明对未知仓库的泛化能力。冻结正式实验时还应新增未参与规则开发的外部留出集。

## 2. 技术栈与质量

| 技术栈标签 | 候选数 |
| --- | --- |
| .NET 10 | 4 |
| .NET 5 | 1 |
| .NET 6 | 1 |
| .NET 8 | 5 |
| .NET 9 | 4 |
| .NET Core 3.1 | 1 |
| .NET Framework | 10 |
| CommunityToolkit.Mvvm | 2 |
| Fluent UI Gallery | 1 |
| MVVM | 21 |
| MVVM Light | 1 |
| MvvmCross | 1 |
| Prism | 2 |
| SQL Server | 1 |
| WPF | 25 |
| WinUI 3 | 1 |
| Windows 系统集成 | 1 |
| 下载管理 | 1 |
| 代码工具 | 1 |
| 控件 Gallery | 1 |
| 网络管理 | 1 |
| 金融可视化 | 1 |

| 活跃度 | 候选数 |
| --- | --- |
| 3 年内更新 | 3 |
| 90 天内活跃 | 16 |
| 已归档 | 2 |
| 超过 3 年未更新 | 5 |

| 许可证 | 候选数 |
| --- | --- |
| Apache-2.0 | 1 |
| GPL-3.0 | 3 |
| MIT | 13 |
| MS-PL | 3 |
| Unlicense | 1 |
| 未声明 | 4 |
| 自定义 MIT（含实体排除条款） | 1 |

Star 最小值/中位数/均值/最大值分别为 39 / 3217.5 / 5829.04 / 27326；分析 ref 的提交数中位数为 851.5。

## 3. 解析器优化前后

下表仅比较 PDF 中的 22 个原始候选；4 个补充候选依流程在优化后搜索，不混入优化前基线。

| 指标 | PDF 原始基线 | PDF 原始优化后 |
| --- | --- | --- |
| 七阶段成功率 | 9/22 (40.91%) | 22/22 (100.00%) |
| 文件解析成功率 | 4238/4239 (99.98%) | 4056/4056 (100.00%) |
| 文件解析失败 | 1 | 0 |
| 同名输出覆盖 | 174 | 0 |
| 识别页面 | 547 | 576 |
| 累计解析时长（秒） | 4173.602 | 98.638 |

补充候选初次解析成功 4/4；全部候选最终成功 26/26。
PDF 原始候选累计耗时缩短为基线的 42.31 倍。

### 解析器调整

- 可信输入路径发现：排除 bin、obj、Generated Files、IDE 和 node_modules 产物，拒绝越界符号链接，并保证顺序确定；影响：Record-Book-App-WPF-MVVM, Login-In-WPF-MVVM-C-Sharp-and-SQL-Server, NETworkManager；回归：离线路径回归通过；Record Book C# 输入从 172 降为 8
- C# 历史编码兼容：严格 UTF-8 失败时按 Windows-1252/Latin-1 有日志回退；影响：VisualHFT；回归：VisualHFT C# 失败数从 1 降为 0，编码回归通过
- Application 派生根节点识别：将 MvxApplication 等自定义 Application 根类型与普通页面分离；影响：MvvmCross；回归：MvvmCross 页面数从 9 修正为 8，根节点回归通过
- C# 引用合并正则索引：将逐类型七次扫描改为按类型集合缓存的合并模式；影响：Playnite, 1Remote, VisualHFT, ILSpy, EarTrumpet, ScreenToGif；回归：七种引用语义回归通过；Playnite 总耗时从 2411.208 秒降为 68.439 秒
- SCC 循环依赖压缩：将真实循环依赖压缩后生成确定性拓扑顺序，同时显式记录 cycle_groups；影响：1Remote, Accelerider.Windows, EarTrumpet, Flow.Launcher, ILSpy, LLPlayer, ModernFlyouts, Playnite, ScreenToGif, SimpleTrader, VisualHFT, ai-dev-gallery；回归：12 个原始候选由第 3 阶段失败恢复为七阶段通过
- 多 csproj 资源合并与缺失项目容错：合并全部项目文件并按各 csproj 目录验证资源；缺失时输出可审计空结果；影响：Page-Navigation-using-MVVM, Playnite, TumblThree, Accelerider.Windows；回归：Page Navigation 资源阶段恢复，单/多/缺失 csproj 回归均通过
- 批量资源引用索引：页面与间接资源仅加载一次，所有文件名变体一次扫描建立 Style/Template 反向索引；影响：Playnite, WPF-Samples, wpfui, NETworkManager；回归：静态资源单/多项目回归通过，Playnite 155 个静态资源可完成分析
- 仓库相对路径唯一标识：用带扩展名的仓库相对 POSIX 路径标识源码和页面，解析、依赖、控件树、迁移、baseline 与评测均镜像目录输出；影响：Accelerider.Windows, Playnite, EarTrumpet, 1Remote, VisualHFT, ModernFlyouts, ILSpy, TumblThree；回归：26 个候选共 5323 个 C#/XAML/csproj 输入全部解析，输出覆盖由 172 次降为 0；跨目录同名、大小写差异和旧 schema 拒绝回归通过
- 同名页面依赖消歧与 SCC 调度：使用完整 x:Class、当前 namespace 和显式限定名消歧同名窗口，并压缩真实页面循环依赖；影响：Playnite；回归：Playnite Desktop/Fullscreen 两套同名窗口不再交叉误连；95 个页面生成路径 ID 调度，保留 2 个真实循环组和 2 条未猜测的歧义记录

## 4. 最终数据集概况

正式实验对象为 20 个：保留 6 个，条件保留 14 个。
合计覆盖 4780 个 C#/XAML/csproj 输入、754 个页面和 754 份控件树。

| 仓库 | 来源 | 状态 | Star | 提交 | 页面 | 技术栈 | 许可证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lbugnion/mvvmlight | PDF | 条件保留 | 1185 | 323 | 1 | WPF, MVVM Light, .NET Framework | MIT |
| MvvmCross/MvvmCross | PDF | 保留 | 3921 | 9934 | 8 | WPF, MvvmCross, MVVM, .NET 8 | MS-PL |
| PrismLibrary/Prism | PDF | 条件保留 | 6821 | 2846 | 6 | WPF, Prism, MVVM, .NET Framework | MIT |
| RJCodeAdvance/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server | PDF | 保留 | 73 | 5 | 3 | WPF, MVVM, .NET Framework, SQL Server | Unlicense |
| umlx5h/LLPlayer | PDF | 条件保留 | 3950 | 356 | 38 | WPF, MVVM, .NET 9 | GPL-3.0 |
| Accelerider/Accelerider.Windows | PDF | 条件保留 | 1525 | 535 | 52 | WPF, Prism, MVVM, .NET Framework | MIT |
| NickeManarin/ScreenToGif | PDF | 保留 | 27326 | 1382 | 61 | WPF, MVVM, .NET 10 | MS-PL |
| JosefNemec/Playnite | PDF | 条件保留 | 13572 | 3981 | 95 | WPF, MVVM, .NET Framework | MIT |
| Flow-Launcher/Flow.Launcher | PDF | 保留 | 15227 | 11581 | 36 | WPF, MVVM, .NET 9 | MIT |
| File-New-Project/EarTrumpet | PDF | 条件保留 | 11215 | 1771 | 7 | WPF, MVVM, .NET 9 | 自定义 MIT（含实体排除条款） |
| 1Remote/1Remote | PDF | 条件保留 | 5992 | 1304 | 47 | WPF, MVVM, .NET 8 | GPL-3.0 |
| VisualHFT/VisualHFT | PDF | 条件保留 | 1159 | 541 | 46 | WPF, MVVM, .NET 8, 金融可视化 | Apache-2.0 |
| snoopwpf/snoopwpf | PDF | 条件保留 | 2514 | 1965 | 3 | WPF, .NET Framework | MS-PL |
| SlimeNull/OpenGptChat | PDF | 条件保留 | 149 | 131 | 5 | WPF, MVVM, .NET 8 | MIT |
| ModernFlyouts-Community/ModernFlyouts | PDF | 条件保留 | 4065 | 473 | 19 | WPF, .NET Framework, Windows 系统集成 | MIT |
| icsharpcode/ILSpy | PDF | 条件保留 | 25697 | 8035 | 24 | WPF, MVVM, .NET 8, 代码工具 | MIT |
| microsoft/WPF-Samples | 补充 | 保留 | 5709 | 653 | 73 | WPF, CommunityToolkit.Mvvm, .NET 10, 控件 Gallery | MIT |
| lepoco/wpfui | 补充 | 保留 | 9543 | 2137 | 85 | WPF, CommunityToolkit.Mvvm, .NET 10, Fluent UI Gallery | MIT |
| BornToBeRoot/NETworkManager | 补充 | 条件保留 | 8491 | 4774 | 125 | WPF, MVVM, .NET 10, 网络管理 | GPL-3.0 |
| TumblThreeApp/TumblThree | 补充 | 条件保留 | 728 | 1050 | 20 | WPF, MVVM, .NET Framework, 下载管理 | MIT |

## 5. 数据集多轴分类

当前分类版本为 1。分类同时记录领域、项目形态、页面规模、迁移挑战和建议实验角色；各轴用途不同，不合并成单一“质量分”。

逐项目机器可读分类由本脚本写入 `results/dataset/dataset-statistics.json` 的 `taxonomy.projects`，后续抽样脚本应读取该字段，不应复制另一份仓库名单。

页面规模由阶段一识别的页面 ID 数量确定：微型 1～5 页、小型 6～19 页、中型 20～49 页、大型 50～99 页、超大型 100 页及以上。它只表示实验规模，不等同于迁移难度；自定义控件、框架导航、平台 API、插件架构和外部服务等复杂性由挑战标签单独表达。

| 领域 | 仓库数 |
| --- | --- |
| 媒体与游戏 | 3 |
| 开发者工具 | 2 |
| 控件与样式 Gallery | 2 |
| 文件与下载 | 2 |
| 框架与架构 | 3 |
| 桌面效率与系统集成 | 3 |
| 网络与远程管理 | 2 |
| 通用业务与交互 | 2 |
| 金融可视化 | 1 |

| 项目形态 | 仓库数 |
| --- | --- |
| 业务应用 | 14 |
| 低复杂度样例 | 1 |
| 控件 Gallery | 2 |
| 框架样例 | 3 |

| 页面规模 | 仓库数 |
| --- | --- |
| 中型（20～49 页） | 6 |
| 大型（50～99 页） | 5 |
| 小型（6～19 页） | 4 |
| 微型（1～5 页） | 4 |
| 超大型（100 页及以上） | 1 |

| 建议实验角色 | 仓库数 |
| --- | --- |
| 主业务集 | 5 |
| 低复杂度 sanity | 2 |
| 压力集 | 7 |
| 平台专项 | 2 |
| 框架导航专项 | 2 |
| 组件映射专项 | 2 |

| 仓库 | 领域 | 形态 | 页面规模 | 迁移挑战 | 建议实验角色 |
| --- | --- | --- | --- | --- | --- |
| mvvmlight | 框架与架构 | 框架样例 | 微型（1～5 页）；实际 1 页 | 历史框架、单页 | 低复杂度 sanity |
| MvvmCross | 框架与架构 | 框架样例 | 小型（6～19 页）；实际 8 页 | MvvmCross 导航、Playground | 框架导航专项 |
| Prism | 框架与架构 | 框架样例 | 小型（6～19 页）；实际 6 页 | Prism 导航、模块化、历史版本 | 框架导航专项 |
| Login-In-WPF-MVVM-C-Sharp-and-SQL-Server | 通用业务与交互 | 业务应用 | 微型（1～5 页）；实际 3 页 | 外部数据库、小样本 | 主业务集 |
| LLPlayer | 媒体与游戏 | 业务应用 | 中型（20～49 页）；实际 38 页 | 自定义控件、媒体能力、GPL-3.0 | 压力集 |
| Accelerider.Windows | 文件与下载 | 业务应用 | 大型（50～99 页）；实际 52 页 | Prism 导航、自定义控件、页面依赖待核验 | 主业务集 |
| ScreenToGif | 媒体与游戏 | 业务应用 | 大型（50～99 页）；实际 61 页 | 自定义控件、屏幕捕获、大规模 | 压力集 |
| Playnite | 媒体与游戏 | 业务应用 | 大型（50～99 页）；实际 95 页 | 多形态 UI、主题系统、大规模 | 压力集 |
| Flow.Launcher | 桌面效率与系统集成 | 业务应用 | 中型（20～49 页）；实际 36 页 | 插件架构、系统集成、自定义控件 | 主业务集 |
| EarTrumpet | 桌面效率与系统集成 | 业务应用 | 小型（6～19 页）；实际 7 页 | Windows 音频、系统集成、自定义许可 | 平台专项 |
| 1Remote | 网络与远程管理 | 业务应用 | 中型（20～49 页）；实际 47 页 | 远程协议、高未决依赖、GPL-3.0 | 压力集 |
| VisualHFT | 金融可视化 | 业务应用 | 中型（20～49 页）；实际 46 页 | 实时可视化、插件架构、高未决依赖 | 压力集 |
| snoopwpf | 开发者工具 | 低复杂度样例 | 微型（1～5 页）；实际 3 页 | 非业务子项目、小样本 | 低复杂度 sanity |
| OpenGptChat | 通用业务与交互 | 业务应用 | 微型（1～5 页）；实际 5 页 | 外部 AI API、小样本 | 主业务集 |
| ModernFlyouts | 桌面效率与系统集成 | 业务应用 | 小型（6～19 页）；实际 19 页 | Windows Shell、已归档、自定义控件 | 平台专项 |
| ILSpy | 开发者工具 | 业务应用 | 中型（20～49 页）；实际 24 页 | 复杂开发者工具、历史 WPF 版本、自定义控件 | 压力集 |
| WPF-Samples | 控件与样式 Gallery | 控件 Gallery | 大型（50～99 页）；实际 73 页 | Gallery、业务流程弱、自定义控件 | 组件映射专项 |
| wpfui | 控件与样式 Gallery | 控件 Gallery | 大型（50～99 页）；实际 85 页 | Gallery、第三方控件、样式密集 | 组件映射专项 |
| NETworkManager | 网络与远程管理 | 业务应用 | 超大型（100 页及以上）；实际 125 页 | 大规模、网络与系统能力、GPL-3.0 | 压力集 |
| TumblThree | 文件与下载 | 业务应用 | 中型（20～49 页）；实际 20 页 | 旧项目格式、下载队列、候选依赖多 | 主业务集 |

### 5.1 后续分层实验建议

- 阶段一完整性实验继续覆盖全部 20 个项目，报告文件、结构、语义引用和资源闭包，不按实验角色删减。
- 主业务集用于比较端到端页面迁移质量；低复杂度 sanity、框架导航、组件映射和平台专项分别报告，不并入同一个业务主指标。
- 压力集按页面规模、根类型、自定义控件比例和未决依赖分层抽样，固定 page ID 与抽样清单；不得只挑选最容易迁移的页面。
- 平台专项只对可迁移的 UI、状态和交互合同评分；Windows 音频、Shell、屏幕捕获和远程协议不得伪装成 React Web 已实现能力。
- 组件映射专项重点测量 WPF/第三方控件到 MUI 的选择和视觉保真，Gallery 的重复控件页面不得主导业务流程指标。
- 每个类别先计算仓库内指标，再对仓库和类别做宏平均；页面数加权的微平均只作为补充，避免 Playnite、NETworkManager 等大型项目淹没小型场景。
- 已知解析缺口涉及的页面或 C# 文件必须先修复，或在冻结 GT 时显式排除并报告；不能把输入缺口归因于迁移模型。
- 正式比较统一冻结仓库 commit、目标路径、数据集分类版本、页面清单、模型、提示词、调用预算和随机种子。

## 6. 补充搜索终止条件

新增 4 个候选，上限为 10。
- `site:github.com WPF MVVM application stars MIT language:C# GitHub`
- `site:github.com WPF UI gallery MVVM MIT GitHub`
- `topic:wpf language:C# stars:>500 sort:updated`
- `wpf mvvm language:C# stars:>200 sort:updated`

新增 4 个候选已补齐官方 .NET 10 WPF、Fluent 控件 Gallery、现代大型网络工具和中型 MIT 业务应用；后续高排名结果主要是重复的控件库/框架、非 WPF 技术栈或过大且无明显增量价值的媒体应用，因此在 10 个上限前按“无明显补充价值”条件停止。

### 已考察但未新增

- neelabo/NeeView：选定主项目含 2142 个 C# 文件，与已有媒体应用重复且适配成本过高
- Kinnara/ModernWpf：主体为控件库，与已新增的两个现代 Gallery 重复
- Keboo/MaterialDesignInXaml.Examples：与 WPF Gallery/Wpf.Ui Gallery 的样式和控件演示覆盖高度重复
- AvaloniaUI/Avalonia：Avalonia 而非 WPF
- abravodev/winforms-mvvm：WinForms 而非 WPF

## 7. 未解决问题

- Playnite 仍有 2 条 MainWindow 短名引用无法仅凭静态 namespace 唯一解析；依赖图明确记录为 ambiguous_references，未建立猜测性边。
- 本机为 macOS，且候选源码按不可信输入处理；未执行 Windows 构建、候选测试、安装脚本或业务运行时验证。
- Page-Navigation-using-MVVM 已淘汰：缺少 .csproj，无法复现原始 WPF 构建，且实际存在的 16 张图片和 2 个字体均未进入资源解析结果。
- SnoopLogo 仅条件保留为低复杂度端到端 sanity 样本；缺少复杂 MVVM 业务、数据流和导航场景。
- GPL-3.0 与 EarTrumpet 自定义许可的后续分发义务需单独处理；未声明许可的 4 个 PDF 候选已淘汰。
- repos/、outputs/ 和 results/ 均为 Git 忽略的本地状态；数据集不再分发他人源码，通过 URL、commit SHA、稀疏路径和复现命令重建。

## 8. 阶段一解析完整性

本节按产物一一对应、结构保留、语义引用显式化和资源闭包审计阶段一结果。解析率中的“已处理”包含显式 unsupported/unresolved，因此它衡量覆盖和可审计性，不是人工 GT 下的语义正确率。

- 工程执行：20/20 个项目七阶段成功。
- 文件覆盖：4780/4780 个 C#/XAML/csproj 输入具有产物；缺失 0，重复 source ID 0，输出覆盖 0。
- XAML：193863 个原始元素全部进入 IR；静默未分类 0，迁移侧视觉差额 0。
- C#：tree-sitter ERROR 199，missing 9，未报告诊断 0，声明差额 31。
- 资源与页面：解析器未解释资源引用 0；页面迁移顺序 754/754，当前歧义边 2。
- 七解析器宏平均 99.69%，阈值 90%，结论为通过。

### 分解析器解析率

| 解析器 | 已处理/应处理 | 解析率 | 结论 |
| --- | --- | --- | --- |
| C# 结构解析器 | 59665/59696 | 99.95% | 通过 |
| XAML/csproj 解析器 | 234945/234945 | 100.00% | 通过 |
| C# 依赖解析器 | 8170/8170 | 100.00% | 通过 |
| 间接资源解析器 | 60/60 | 100.00% | 通过 |
| 页面依赖解析器 | 1034/1056 | 97.92% | 通过 |
| 静态资源解析器 | 21590/21598 | 99.96% | 通过 |
| 控件依赖解析器 | 22601/22601 | 100.00% | 通过 |

更严格的“单项目内每类解析器均达阈值”口径仍有局部低样本项：MvvmCross 的静态资源解析器 85.71%；Prism 的页面依赖解析器 78.57%；Accelerider.Windows 的页面依赖解析器 80.88%；snoopwpf 的静态资源解析器 80.00%。它们不阻塞跨项目聚合验收，但必须在对应类别实验中单独披露。

两次完整运行比较 5654 个结构化产物，一致 5654 个；统计报告一致 25/25，确定性结论为通过。

完整审计方法、问题聚类和剩余限制见[阶段一解析完整性两遍式审计](parser-completeness-audit.md)。
