# WPF 实验数据集现状统计

数据冻结时间：2026-07-22T16:53:42.332392+00:00。

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

## 5. 补充搜索终止条件

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

## 6. 未解决问题

- Playnite 仍有 2 条 MainWindow 短名引用无法仅凭静态 namespace 唯一解析；依赖图明确记录为 ambiguous_references，未建立猜测性边。
- 本机为 macOS，且候选源码按不可信输入处理；未执行 Windows 构建、候选测试、安装脚本或业务运行时验证。
- Page-Navigation-using-MVVM 已淘汰：缺少 .csproj，无法复现原始 WPF 构建，且实际存在的 16 张图片和 2 个字体均未进入资源解析结果。
- SnoopLogo 仅条件保留为低复杂度端到端 sanity 样本；缺少复杂 MVVM 业务、数据流和导航场景。
- GPL-3.0 与 EarTrumpet 自定义许可的后续分发义务需单独处理；未声明许可的 4 个 PDF 候选已淘汰。
- repos/、outputs/ 和 results/ 均为 Git 忽略的本地状态；数据集不再分发他人源码，通过 URL、commit SHA、稀疏路径和复现命令重建。
