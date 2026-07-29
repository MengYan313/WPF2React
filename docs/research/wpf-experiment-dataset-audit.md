# WPF 实验数据集逐项目排查记录

数据冻结时间：2026-07-24T11:29:46.364375+00:00。

每个项目均只进行静态读取和解析，未执行候选仓库脚本、构建或安装命令。

## 0. 筛选与分类方法

筛选先执行源技术栈、许可证、固定提交和项目定义等硬约束，再综合领域增量、项目形态、规模梯度、社区与维护证据决定保留或条件保留。Star 和活跃度只作为辅助证据；七阶段成功只证明当前解析器可处理，不证明项目可构建或迁移正确。

正式项目使用分类版本 1，分别记录领域、项目形态、页面规模、迁移挑战和建议实验角色。页面规模由阶段一页面 ID 数量确定；挑战标签用于记录框架导航、自定义控件、平台 API、插件、外部服务和许可证等不可由页面数表达的因素。复杂项目进入压力集或平台专项，不因难迁移而直接淘汰。

淘汰条件包括未声明许可证、缺少可复现工程定义、源技术栈不属于 WPF，以及与已有候选高度重复且没有覆盖增量。当前 20 个正式项目参与过解析器问题发现，未来还需使用未参与规则开发的外部留出集验证泛化能力。

## 1. SingletonSean/SimpleTrader

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/SingletonSean/SimpleTrader |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | master |
| 固定 commit | 564e87a4299498062de33df97b43a0347aead463 |
| 目标路径 | SimpleTrader/SimpleTrader.WPF |
| Star / 提交数 | 317 / 66 |
| 最后推送 / 活跃度 | 2023-10-05T11:05:37Z / 3 年内更新 |
| 语言 / 许可证 | C# / 未声明 |
| 技术栈 | WPF, MVVM, .NET Core 3.1 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | 审计时使用 partial clone + sparse-checkout；本地副本已按筛选结论删除 |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 56/0 | 56/0 |
| XML 成功/失败 | 17/0 | 17/0 |
| 页面/控件树 | 12/12 | 13/13 |
| 同名输出覆盖 | 1 | 0 |
| 耗时（秒） | 0.403 | 0.114 |

失败原因：基线在 C# 循环依赖处失败，优化后七阶段通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**淘汰**。仓库未声明开源许可证；源码虽可解析，但不适合纳入可复现开源数据集

已知限制：无。

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/SingletonSean/SimpleTrader.git repos/SimpleTrader
git -C repos/SimpleTrader fetch --depth 1 origin 564e87a4299498062de33df97b43a0347aead463
git -C repos/SimpleTrader sparse-checkout set -- SimpleTrader/SimpleTrader.WPF
git -C repos/SimpleTrader checkout --detach 564e87a4299498062de33df97b43a0347aead463
.venv/bin/python scripts/run_dataset_parse.py SimpleTrader --output-base-dir outputs/dataset-analysis/final
```

## 2. MarkWithall/worlds-simplest-csharp-wpf-mvvm-example

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/MarkWithall/worlds-simplest-csharp-wpf-mvvm-example |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | C#9.0 |
| 固定 commit | 27297a5801132ea1c9c3a01fc2e48b236fbf68aa |
| 目标路径 | MinimalMVVM |
| Star / 提交数 | 371 / 28 |
| 最后推送 / 活跃度 | 2021-01-30T19:37:18Z / 超过 3 年未更新 |
| 语言 / 许可证 | C# / 未声明 |
| 技术栈 | WPF, MVVM, .NET 5 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | 审计时使用 partial clone + sparse-checkout；本地副本已按筛选结论删除 |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 7/0 | 7/0 |
| XML 成功/失败 | 4/0 | 4/0 |
| 页面/控件树 | 2/2 | 2/2 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.035 | 0.026 |

失败原因：基线与最终解析均通过。

相关解析器调整：无。

最终结论：**淘汰**。仓库未声明开源许可证；仅有 2 个页面，与已纳入的小型样例重复

已知限制：分析的 C#9.0 分支自 2021 年起未更新

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/MarkWithall/worlds-simplest-csharp-wpf-mvvm-example.git repos/worlds-simplest-csharp-wpf-mvvm-example
git -C repos/worlds-simplest-csharp-wpf-mvvm-example fetch --depth 1 origin 27297a5801132ea1c9c3a01fc2e48b236fbf68aa
git -C repos/worlds-simplest-csharp-wpf-mvvm-example sparse-checkout set -- MinimalMVVM
git -C repos/worlds-simplest-csharp-wpf-mvvm-example checkout --detach 27297a5801132ea1c9c3a01fc2e48b236fbf68aa
.venv/bin/python scripts/run_dataset_parse.py worlds-simplest-csharp-wpf-mvvm-example --output-base-dir outputs/dataset-analysis/final
```

## 3. lbugnion/mvvmlight

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/lbugnion/mvvmlight |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | master |
| 固定 commit | aa657f7150730ea9d82d1077ffa0038affc400ca |
| 目标路径 | Samples/MvvmLightDragAndDrop/MvvmLightDragAndDrop |
| Star / 提交数 | 1185 / 323 |
| 最后推送 / 活跃度 | 2021-08-13T12:43:37Z / 已归档 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM Light, .NET Framework |
| 领域 | 框架与架构 |
| 项目形态 | 框架样例 |
| 页面规模 | 微型（1～5 页）；实际 1 页 |
| 迁移挑战 | 历史框架、单页 |
| 建议实验角色 | 低复杂度 sanity |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 4/0 | 4/0 |
| XML 成功/失败 | 4/0 | 4/0 |
| 页面/控件树 | 1/1 | 1/1 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.036 | 0.029 |

失败原因：基线与最终解析均通过。

相关解析器调整：无。

最终结论：**条件保留**。具有历史性 MVVM 框架样例价值；MIT 许可且解析稳定

已知限制：仓库已归档；选取子项目仅 1 个页面

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/lbugnion/mvvmlight.git repos/mvvmlight
git -C repos/mvvmlight fetch --depth 1 origin aa657f7150730ea9d82d1077ffa0038affc400ca
git -C repos/mvvmlight sparse-checkout set -- Samples/MvvmLightDragAndDrop/MvvmLightDragAndDrop
git -C repos/mvvmlight checkout --detach aa657f7150730ea9d82d1077ffa0038affc400ca
.venv/bin/python scripts/run_dataset_parse.py mvvmlight --output-base-dir outputs/dataset-analysis/final
```

## 4. 944095635/MVVM

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/944095635/MVVM |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | master |
| 固定 commit | 2abea0795ac03db5f039f7d0887289bdd149dead |
| 目标路径 | MVVM |
| Star / 提交数 | 159 / 27 |
| 最后推送 / 活跃度 | 2021-11-28T03:40:10Z / 超过 3 年未更新 |
| 语言 / 许可证 | C# / 未声明 |
| 技术栈 | WPF, MVVM, .NET Framework |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | 审计时使用 partial clone + sparse-checkout；本地副本已按筛选结论删除 |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 14/0 | 14/0 |
| XML 成功/失败 | 6/0 | 6/0 |
| 页面/控件树 | 4/4 | 4/4 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.061 | 0.038 |

失败原因：基线与最终解析均通过。

相关解析器调整：无。

最终结论：**淘汰**。仓库未声明开源许可证；PDF 已标注实现不规范且长期未更新

已知限制：仅 27 个提交

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/944095635/MVVM.git repos/MVVM
git -C repos/MVVM fetch --depth 1 origin 2abea0795ac03db5f039f7d0887289bdd149dead
git -C repos/MVVM sparse-checkout set -- MVVM
git -C repos/MVVM checkout --detach 2abea0795ac03db5f039f7d0887289bdd149dead
.venv/bin/python scripts/run_dataset_parse.py MVVM --output-base-dir outputs/dataset-analysis/final
```

## 5. MvvmCross/MvvmCross

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/MvvmCross/MvvmCross |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | develop |
| 固定 commit | 20e345d7b56dc64c079783f5337a21bd6a50136d |
| 目标路径 | Projects/Playground/Playground.WpfCore |
| Star / 提交数 | 3921 / 9934 |
| 最后推送 / 活跃度 | 2026-07-21T05:57:43Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MS-PL |
| 技术栈 | WPF, MvvmCross, MVVM, .NET 8 |
| 领域 | 框架与架构 |
| 项目形态 | 框架样例 |
| 页面规模 | 小型（6～19 页）；实际 8 页 |
| 迁移挑战 | MvvmCross 导航、Playground |
| 建议实验角色 | 框架导航专项 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 9/0 | 9/0 |
| XML 成功/失败 | 10/0 | 10/0 |
| 页面/控件树 | 9/9 | 8/8 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.044 | 0.032 |

失败原因：基线通过；App.xaml 的 MvxApplication 曾被误计为页面，最终修正为根节点。

相关解析器调整：Application 派生根节点识别

最终结论：**保留**。PDF 星标候选；持续活跃且 WPF Playground 解析完整

已知限制：选取的是框架 Playground，不是完整业务应用

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/MvvmCross/MvvmCross.git repos/MvvmCross
git -C repos/MvvmCross fetch --depth 1 origin 20e345d7b56dc64c079783f5337a21bd6a50136d
git -C repos/MvvmCross sparse-checkout set -- Projects/Playground/Playground.WpfCore
git -C repos/MvvmCross checkout --detach 20e345d7b56dc64c079783f5337a21bd6a50136d
.venv/bin/python scripts/run_dataset_parse.py MvvmCross --output-base-dir outputs/dataset-analysis/final
```

## 6. PrismLibrary/Prism

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/PrismLibrary/Prism |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | v8.1.97 |
| 固定 commit | 15140a61976d0a224cd6ebb9ee1f7ca63db02b47 |
| 目标路径 | e2e/Wpf/HelloWorld, e2e/Wpf/HelloWorld.Core, e2e/Wpf/Modules/HelloWorld.Modules.ModuleA |
| Star / 提交数 | 6821 / 2846 |
| 最后推送 / 活跃度 | 2026-07-10T15:12:41Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, Prism, MVVM, .NET Framework |
| 领域 | 框架与架构 |
| 项目形态 | 框架样例 |
| 页面规模 | 小型（6～19 页）；实际 6 页 |
| 迁移挑战 | Prism 导航、模块化、历史版本 |
| 建议实验角色 | 框架导航专项 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 17/0 | 15/0 |
| XML 成功/失败 | 13/0 | 11/0 |
| 页面/控件树 | 6/6 | 6/6 |
| 同名输出覆盖 | 2 | 0 |
| 耗时（秒） | 0.099 | 0.051 |

失败原因：当前 master 基线通过；因当前许可条款变更，最终改用 v8.1.97 并通过。

相关解析器调整：生成目录过滤; 多 csproj 资源合并

最终结论：**条件保留**。PDF 星标候选；选取的 v8.1.97 是 MIT 许可的稳定 WPF 模块化样例

已知限制：固定在 2021 年历史版本；不得将许可结论扩展到当前 Prism 版本

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/PrismLibrary/Prism.git repos/Prism
git -C repos/Prism fetch --depth 1 origin 15140a61976d0a224cd6ebb9ee1f7ca63db02b47
git -C repos/Prism sparse-checkout set -- e2e/Wpf/HelloWorld e2e/Wpf/HelloWorld.Core e2e/Wpf/Modules/HelloWorld.Modules.ModuleA
git -C repos/Prism checkout --detach 15140a61976d0a224cd6ebb9ee1f7ca63db02b47
.venv/bin/python scripts/run_dataset_parse.py Prism --output-base-dir outputs/dataset-analysis/final
```

## 7. CSharpDesignPro/Page-Navigation-using-MVVM

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/CSharpDesignPro/Page-Navigation-using-MVVM |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | a4c42a26c82bde793e6a83960f1534fb1956305e |
| 目标路径 | . |
| Star / 提交数 | 323 / 5 |
| 最后推送 / 活跃度 | 2022-08-25T15:31:26Z / 超过 3 年未更新 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM, .NET Framework |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | 审计时使用 partial clone + sparse-checkout；本地副本已按筛选结论删除 |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | resource_dependency | 无 |
| C# 成功/失败 | 21/0 | 21/0 |
| XML 成功/失败 | 14/0 | 14/0 |
| 页面/控件树 | 8/8 | 8/8 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.08 | 0.059 |

失败原因：基线因不存在 csproj 而在资源阶段失败；最终虽产生明确的空资源结果并通过，但仓库实际存在的 16 张图片和 2 个字体均未进入资源解析结果。

相关解析器调整：缺失 csproj 的显式空结果

最终结论：**淘汰**。缺少 .csproj，无法复现原始 WPF 构建；实际存在的 16 张图片和 2 个字体未进入资源解析结果，资源完整性不满足正式实验要求

已知限制：8 个页面和 C# 源码可静态解析，但不能替代原始工程构建复现；仅 5 个提交

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/CSharpDesignPro/Page-Navigation-using-MVVM.git repos/Page-Navigation-using-MVVM
git -C repos/Page-Navigation-using-MVVM fetch --depth 1 origin a4c42a26c82bde793e6a83960f1534fb1956305e
git -C repos/Page-Navigation-using-MVVM sparse-checkout set -- .
git -C repos/Page-Navigation-using-MVVM checkout --detach a4c42a26c82bde793e6a83960f1534fb1956305e
.venv/bin/python scripts/run_dataset_parse.py Page-Navigation-using-MVVM --output-base-dir outputs/dataset-analysis/final
```

## 8. RJCodeAdvance/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/RJCodeAdvance/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | b7268c06b1a70b2dc2cdbf27bb04cc7967c58030 |
| 目标路径 | WPF-LoginForm |
| Star / 提交数 | 73 / 5 |
| 最后推送 / 活跃度 | 2022-09-12T21:45:56Z / 超过 3 年未更新 |
| 语言 / 许可证 | C# / Unlicense |
| 技术栈 | WPF, MVVM, .NET Framework, SQL Server |
| 领域 | 通用业务与交互 |
| 项目形态 | 业务应用 |
| 页面规模 | 微型（1～5 页）；实际 3 页 |
| 迁移挑战 | 外部数据库、小样本 |
| 建议实验角色 | 主业务集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 28/0 | 13/0 |
| XML 成功/失败 | 5/0 | 5/0 |
| 页面/控件树 | 3/3 | 3/3 |
| 同名输出覆盖 | 2 | 0 |
| 耗时（秒） | 0.255 | 0.044 |

失败原因：基线通过；最终过滤 obj 后 C# 输入从 28 个恢复为 13 个真实源文件。

相关解析器调整：生成目录过滤

最终结论：**保留**。登录场景清晰且规模适合小型实验；Unlicense 且最终无解析覆盖

已知限制：仅 5 个提交；依赖 SQL Server 的运行部分未执行

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/RJCodeAdvance/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server.git repos/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server
git -C repos/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server fetch --depth 1 origin b7268c06b1a70b2dc2cdbf27bb04cc7967c58030
git -C repos/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server sparse-checkout set -- WPF-LoginForm
git -C repos/Login-In-WPF-MVVM-C-Sharp-and-SQL-Server checkout --detach b7268c06b1a70b2dc2cdbf27bb04cc7967c58030
.venv/bin/python scripts/run_dataset_parse.py Login-In-WPF-MVVM-C-Sharp-and-SQL-Server --output-base-dir outputs/dataset-analysis/final
```

## 9. TacticDevGit/Record-Book-App-WPF-MVVM

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/TacticDevGit/Record-Book-App-WPF-MVVM |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | 25cdfe1be09eb161bf526717f56bb2ab2f55bc53 |
| 目标路径 | Record Book MVVM |
| Star / 提交数 | 39 / 1 |
| 最后推送 / 活跃度 | 2023-04-27T17:57:55Z / 超过 3 年未更新 |
| 语言 / 许可证 | C# / 未声明 |
| 技术栈 | WPF, MVVM, .NET 6 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | 审计时使用 partial clone + sparse-checkout；本地副本已按筛选结论删除 |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 172/0 | 8/0 |
| XML 成功/失败 | 4/0 | 4/0 |
| 页面/控件树 | 2/2 | 2/2 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.297 | 0.048 |

失败原因：基线被 164 个已跟踪 obj 生成文件污染；过滤后 8 个真实 C# 文件解析通过。

相关解析器调整：生成目录过滤

最终结论：**淘汰**。仓库未声明开源许可证；仅 1 个提交且将 obj 产物纳入版本控制

已知限制：仅 2 个页面

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/TacticDevGit/Record-Book-App-WPF-MVVM.git repos/Record-Book-App-WPF-MVVM
git -C repos/Record-Book-App-WPF-MVVM fetch --depth 1 origin 25cdfe1be09eb161bf526717f56bb2ab2f55bc53
git -C repos/Record-Book-App-WPF-MVVM sparse-checkout set -- 'Record Book MVVM'
git -C repos/Record-Book-App-WPF-MVVM checkout --detach 25cdfe1be09eb161bf526717f56bb2ab2f55bc53
.venv/bin/python scripts/run_dataset_parse.py Record-Book-App-WPF-MVVM --output-base-dir outputs/dataset-analysis/final
```

## 10. umlx5h/LLPlayer

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/umlx5h/LLPlayer |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | main |
| 固定 commit | da101d87681bb4d1d87a59884bca95043dd1158b |
| 目标路径 | LLPlayer |
| Star / 提交数 | 3950 / 356 |
| 最后推送 / 活跃度 | 2026-07-19T12:20:10Z / 90 天内活跃 |
| 语言 / 许可证 | C# / GPL-3.0 |
| 技术栈 | WPF, MVVM, .NET 9 |
| 领域 | 媒体与游戏 |
| 项目形态 | 业务应用 |
| 页面规模 | 中型（20～49 页）；实际 38 页 |
| 迁移挑战 | 自定义控件、媒体能力、GPL-3.0 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 84/0 | 84/0 |
| XML 成功/失败 | 43/0 | 43/0 |
| 页面/控件树 | 39/39 | 38/38 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 19.862 | 1.289 |

失败原因：基线在 C# 循环依赖处失败，优化后 38 个页面全部通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**条件保留**。PDF 星标候选；活跃的中大型媒体 WPF 应用且无同名覆盖

已知限制：GPL-3.0 的后续分发需遵守相应义务；自定义媒体控件较多

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/umlx5h/LLPlayer.git repos/LLPlayer
git -C repos/LLPlayer fetch --depth 1 origin da101d87681bb4d1d87a59884bca95043dd1158b
git -C repos/LLPlayer sparse-checkout set -- LLPlayer
git -C repos/LLPlayer checkout --detach da101d87681bb4d1d87a59884bca95043dd1158b
.venv/bin/python scripts/run_dataset_parse.py LLPlayer --output-base-dir outputs/dataset-analysis/final
```

## 11. microsoft/ai-dev-gallery

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/microsoft/ai-dev-gallery |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | e61e651983a1edfba4286b3660726d56bc452810 |
| 目标路径 | AIDevGallery |
| Star / 提交数 | 1484 / 1786 |
| 最后推送 / 活跃度 | 2026-07-14T04:35:21Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WinUI 3, MVVM, .NET 9 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | 审计时使用 partial clone + sparse-checkout；本地副本已按筛选结论删除 |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 285/0 | 285/0 |
| XML 成功/失败 | 107/0 | 107/0 |
| 页面/控件树 | 93/93 | 96/96 |
| 同名输出覆盖 | 8 | 0 |
| 耗时（秒） | 82.422 | 2.053 |

失败原因：基线在 C# 循环依赖处失败，优化后可解析；源码检查确认为 WinUI 3 而非 WPF。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**淘汰**。与 WPF → React 实验的源技术栈不符

已知限制：解析器能读取 XAML 不代表场景符合 WPF 数据集定义

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/microsoft/ai-dev-gallery.git repos/ai-dev-gallery
git -C repos/ai-dev-gallery fetch --depth 1 origin e61e651983a1edfba4286b3660726d56bc452810
git -C repos/ai-dev-gallery sparse-checkout set -- AIDevGallery
git -C repos/ai-dev-gallery checkout --detach e61e651983a1edfba4286b3660726d56bc452810
.venv/bin/python scripts/run_dataset_parse.py ai-dev-gallery --output-base-dir outputs/dataset-analysis/final
```

## 12. Accelerider/Accelerider.Windows

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/Accelerider/Accelerider.Windows |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | master |
| 固定 commit | c0d05575d5ae7b44546972857a642a64147678d1 |
| 目标路径 | Source |
| Star / 提交数 | 1525 / 535 |
| 最后推送 / 活跃度 | 2024-11-07T02:02:30Z / 3 年内更新 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, Prism, MVVM, .NET Framework |
| 领域 | 文件与下载 |
| 项目形态 | 业务应用 |
| 页面规模 | 大型（50～99 页）；实际 52 页 |
| 迁移挑战 | Prism 导航、自定义控件、页面依赖待核验 |
| 建议实验角色 | 主业务集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 272/0 | 272/0 |
| XML 成功/失败 | 89/0 | 89/0 |
| 页面/控件树 | 51/51 | 52/52 |
| 同名输出覆盖 | 16 | 0 |
| 耗时（秒） | 91.61 | 1.161 |

失败原因：基线在 C# 循环依赖处失败，优化后通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描; 多 csproj 资源合并

最终结论：**条件保留**。PDF 星标候选；MIT 许可的 Prism 模块化应用，包含 50 个页面

已知限制：最后推送为 2024 年

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/Accelerider/Accelerider.Windows.git repos/Accelerider.Windows
git -C repos/Accelerider.Windows fetch --depth 1 origin c0d05575d5ae7b44546972857a642a64147678d1
git -C repos/Accelerider.Windows sparse-checkout set -- Source
git -C repos/Accelerider.Windows checkout --detach c0d05575d5ae7b44546972857a642a64147678d1
.venv/bin/python scripts/run_dataset_parse.py Accelerider.Windows --output-base-dir outputs/dataset-analysis/final
```

## 13. NickeManarin/ScreenToGif

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/NickeManarin/ScreenToGif |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | master |
| 固定 commit | 27a49c3be69486f2db964290f4f2274e790fb687 |
| 目标路径 | ScreenToGif |
| Star / 提交数 | 27326 / 1382 |
| 最后推送 / 活跃度 | 2026-04-27T19:45:54Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MS-PL |
| 技术栈 | WPF, MVVM, .NET 10 |
| 领域 | 媒体与游戏 |
| 项目形态 | 业务应用 |
| 页面规模 | 大型（50～99 页）；实际 61 页 |
| 迁移挑战 | 自定义控件、屏幕捕获、大规模 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 190/0 | 190/0 |
| XML 成功/失败 | 110/0 | 110/0 |
| 页面/控件树 | 61/61 | 61/61 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 129.46 | 9.953 |

失败原因：基线在 C# 循环依赖处失败，优化后 61 个页面通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**保留**。高 star、持续活跃的完整 WPF 应用；最终无文件解析失败或同名覆盖

已知限制：规模较大，后续迁移实验需分层取样

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/NickeManarin/ScreenToGif.git repos/ScreenToGif
git -C repos/ScreenToGif fetch --depth 1 origin 27a49c3be69486f2db964290f4f2274e790fb687
git -C repos/ScreenToGif sparse-checkout set -- ScreenToGif
git -C repos/ScreenToGif checkout --detach 27a49c3be69486f2db964290f4f2274e790fb687
.venv/bin/python scripts/run_dataset_parse.py ScreenToGif --output-base-dir outputs/dataset-analysis/final
```

## 14. JosefNemec/Playnite

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/JosefNemec/Playnite |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | master |
| 固定 commit | 02fc1972a1f0c4b7e5f2bc2b91d8dfe643141965 |
| 目标路径 | source/Playnite, source/Playnite.DesktopApp, source/Playnite.FullscreenApp, source/Tools/PlayniteInstaller |
| Star / 提交数 | 13572 / 3981 |
| 最后推送 / 活跃度 | 2026-05-26T13:02:02Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM, .NET Framework |
| 领域 | 媒体与游戏 |
| 项目形态 | 业务应用 |
| 页面规模 | 大型（50～99 页）；实际 95 页 |
| 迁移挑战 | 多形态 UI、主题系统、大规模 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 522/0 | 522/0 |
| XML 成功/失败 | 275/0 | 275/0 |
| 页面/控件树 | 82/82 | 95/95 |
| 同名输出覆盖 | 56 | 0 |
| 耗时（秒） | 2411.208 | 68.439 |

失败原因：基线因循环依赖失败且总耗时 2411.208 秒；最终约 51 秒完成七阶段。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描; 多 csproj 资源合并; 批量资源引用索引

最终结论：**条件保留**。PDF 星标候选；高 star、持续活跃且包含桌面/全屏多形态页面

已知限制：规模大，适合作为压力样本而非默认全量迁移样本

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/JosefNemec/Playnite.git repos/Playnite
git -C repos/Playnite fetch --depth 1 origin 02fc1972a1f0c4b7e5f2bc2b91d8dfe643141965
git -C repos/Playnite sparse-checkout set -- source/Playnite source/Playnite.DesktopApp source/Playnite.FullscreenApp source/Tools/PlayniteInstaller
git -C repos/Playnite checkout --detach 02fc1972a1f0c4b7e5f2bc2b91d8dfe643141965
.venv/bin/python scripts/run_dataset_parse.py Playnite --output-base-dir outputs/dataset-analysis/final
```

## 15. Flow-Launcher/Flow.Launcher

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/Flow-Launcher/Flow.Launcher |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | dev |
| 固定 commit | 07a958d19fa69a2e10a258b0cf455f0156ed5989 |
| 目标路径 | Flow.Launcher |
| Star / 提交数 | 15227 / 11581 |
| 最后推送 / 活跃度 | 2026-07-20T22:42:42Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM, .NET 9 |
| 领域 | 桌面效率与系统集成 |
| 项目形态 | 业务应用 |
| 页面规模 | 中型（20～49 页）；实际 36 页 |
| 迁移挑战 | 插件架构、系统集成、自定义控件 |
| 建议实验角色 | 主业务集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 98/0 | 98/0 |
| XML 成功/失败 | 90/0 | 90/0 |
| 页面/控件树 | 36/36 | 36/36 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 27.359 | 3.15 |

失败原因：基线在 C# 循环依赖处失败，优化后 36 个页面通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**保留**。PDF 星标候选；高 star、持续活跃、MIT 许可且无同名覆盖

已知限制：插件生态不在当前稀疏取样范围内

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/Flow-Launcher/Flow.Launcher.git repos/Flow.Launcher
git -C repos/Flow.Launcher fetch --depth 1 origin 07a958d19fa69a2e10a258b0cf455f0156ed5989
git -C repos/Flow.Launcher sparse-checkout set -- Flow.Launcher
git -C repos/Flow.Launcher checkout --detach 07a958d19fa69a2e10a258b0cf455f0156ed5989
.venv/bin/python scripts/run_dataset_parse.py Flow.Launcher --output-base-dir outputs/dataset-analysis/final
```

## 16. File-New-Project/EarTrumpet

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/File-New-Project/EarTrumpet |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | master |
| 固定 commit | 2ad3a97fb17386af7494d1cc751a3a824919f9c0 |
| 目标路径 | EarTrumpet, EarTrumpet.ColorTool |
| Star / 提交数 | 11215 / 1771 |
| 最后推送 / 活跃度 | 2026-07-19T00:43:45Z / 90 天内活跃 |
| 语言 / 许可证 | C# / 自定义 MIT（含实体排除条款） |
| 技术栈 | WPF, MVVM, .NET 9 |
| 领域 | 桌面效率与系统集成 |
| 项目形态 | 业务应用 |
| 页面规模 | 小型（6～19 页）；实际 7 页 |
| 迁移挑战 | Windows 音频、系统集成、自定义许可 |
| 建议实验角色 | 平台专项 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 307/0 | 307/0 |
| XML 成功/失败 | 14/0 | 14/0 |
| 页面/控件树 | 7/7 | 7/7 |
| 同名输出覆盖 | 7 | 0 |
| 耗时（秒） | 195.163 | 1.205 |

失败原因：基线在 C# 循环依赖处失败，优化后通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描; 多 csproj 资源合并

最终结论：**条件保留**。高 star 且持续活跃的 Windows 音频场景；可补充弹出窗口和系统集成页面

已知限制：许可文本存在实体排除条款，不能按标准 MIT 泛化

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/File-New-Project/EarTrumpet.git repos/EarTrumpet
git -C repos/EarTrumpet fetch --depth 1 origin 2ad3a97fb17386af7494d1cc751a3a824919f9c0
git -C repos/EarTrumpet sparse-checkout set -- EarTrumpet EarTrumpet.ColorTool
git -C repos/EarTrumpet checkout --detach 2ad3a97fb17386af7494d1cc751a3a824919f9c0
.venv/bin/python scripts/run_dataset_parse.py EarTrumpet --output-base-dir outputs/dataset-analysis/final
```

## 17. 1Remote/1Remote

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/1Remote/1Remote |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | 5b9d8441104484aaa573dbe3c043cc3d01b18334 |
| 目标路径 | Ui |
| Star / 提交数 | 5992 / 1304 |
| 最后推送 / 活跃度 | 2026-07-14T01:39:43Z / 90 天内活跃 |
| 语言 / 许可证 | C# / GPL-3.0 |
| 技术栈 | WPF, MVVM, .NET 8 |
| 领域 | 网络与远程管理 |
| 项目形态 | 业务应用 |
| 页面规模 | 中型（20～49 页）；实际 47 页 |
| 迁移挑战 | 远程协议、高未决依赖、GPL-3.0 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 254/0 | 254/0 |
| XML 成功/失败 | 91/0 | 91/0 |
| 页面/控件树 | 47/47 | 47/47 |
| 同名输出覆盖 | 1 | 0 |
| 耗时（秒） | 399.793 | 4.975 |

失败原因：基线在 C# 循环依赖处失败，优化后 47 个页面通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**条件保留**。持续活跃的远程连接管理场景；解析覆盖较完整

已知限制：GPL-3.0 的后续分发需遵守相应义务

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/1Remote/1Remote.git repos/1Remote
git -C repos/1Remote fetch --depth 1 origin 5b9d8441104484aaa573dbe3c043cc3d01b18334
git -C repos/1Remote sparse-checkout set -- Ui
git -C repos/1Remote checkout --detach 5b9d8441104484aaa573dbe3c043cc3d01b18334
.venv/bin/python scripts/run_dataset_parse.py 1Remote --output-base-dir outputs/dataset-analysis/final
```

## 18. VisualHFT/VisualHFT

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/VisualHFT/VisualHFT |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | master |
| 固定 commit | 598b16169e1af9b127b98bdc0c73dc3c3b7a54d7 |
| 目标路径 | . |
| Star / 提交数 | 1159 / 541 |
| 最后推送 / 活跃度 | 2026-07-14T23:03:51Z / 90 天内活跃 |
| 语言 / 许可证 | C# / Apache-2.0 |
| 技术栈 | WPF, MVVM, .NET 8, 金融可视化 |
| 领域 | 金融可视化 |
| 项目形态 | 业务应用 |
| 页面规模 | 中型（20～49 页）；实际 46 页 |
| 迁移挑战 | 实时可视化、插件架构、高未决依赖 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 325/1 | 326/0 |
| XML 成功/失败 | 73/0 | 73/0 |
| 页面/控件树 | 33/33 | 46/46 |
| 同名输出覆盖 | 77 | 0 |
| 耗时（秒） | 331.239 | 2.917 |

失败原因：基线有 1 个 Windows-1252 C# 文件失败且循环依赖中止；最终 326 个 C# 文件全部读取并通过。

相关解析器调整：Windows-1252 编码回退; SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**条件保留**。PDF 星标候选；活跃、Apache-2.0 许可且提供金融数据可视化场景

已知限制：插件结构复杂，后续迁移实验建议按路径和插件分层取样

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/VisualHFT/VisualHFT.git repos/VisualHFT
git -C repos/VisualHFT fetch --depth 1 origin 598b16169e1af9b127b98bdc0c73dc3c3b7a54d7
git -C repos/VisualHFT sparse-checkout set -- .
git -C repos/VisualHFT checkout --detach 598b16169e1af9b127b98bdc0c73dc3c3b7a54d7
.venv/bin/python scripts/run_dataset_parse.py VisualHFT --output-base-dir outputs/dataset-analysis/final
```

## 19. snoopwpf/snoopwpf

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/snoopwpf/snoopwpf |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | develop |
| 固定 commit | c04241fb56e72ba46b6e6ce79f1a4c65c020185f |
| 目标路径 | SnoopLogo |
| Star / 提交数 | 2514 / 1965 |
| 最后推送 / 活跃度 | 2026-07-05T12:15:56Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MS-PL |
| 技术栈 | WPF, .NET Framework |
| 领域 | 开发者工具 |
| 项目形态 | 低复杂度样例 |
| 页面规模 | 微型（1～5 页）；实际 3 页 |
| 迁移挑战 | 非业务子项目、小样本 |
| 建议实验角色 | 低复杂度 sanity |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 4/0 | 4/0 |
| XML 成功/失败 | 5/0 | 5/0 |
| 页面/控件树 | 3/3 | 3/3 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.029 | 0.028 |

失败原因：固定 commit c04241fb56e72ba46b6e6ce79f1a4c65c020185f 的 SnoopLogo 子项目基线与最终解析均通过；3 个页面、静态资源和控件树均可解析，且无同名输出覆盖。

相关解析器调整：无。

最终结论：**条件保留**。SnoopLogo 具有完整 .sln/.csproj 和明确的 MS-PL 许可证；3 个页面、静态资源及零同名覆盖适合作为低复杂度端到端迁移 sanity 样本

已知限制：缺少复杂 MVVM 业务、数据流和导航场景，不作为复杂迁移能力的代表性样本；此结论仅针对固定提交中的 SnoopLogo 子项目，不是对整个 Snoop 工具的评价

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/snoopwpf/snoopwpf.git repos/snoopwpf
git -C repos/snoopwpf fetch --depth 1 origin c04241fb56e72ba46b6e6ce79f1a4c65c020185f
git -C repos/snoopwpf sparse-checkout set -- SnoopLogo
git -C repos/snoopwpf checkout --detach c04241fb56e72ba46b6e6ce79f1a4c65c020185f
.venv/bin/python scripts/run_dataset_parse.py snoopwpf --output-base-dir outputs/dataset-analysis/final
```

## 20. SlimeNull/OpenGptChat

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/SlimeNull/OpenGptChat |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | main |
| 固定 commit | 754d5c4e41e31515f287fb53fb5a4e90621bee65 |
| 目标路径 | OpenGptChat |
| Star / 提交数 | 149 / 131 |
| 最后推送 / 活跃度 | 2024-10-04T21:25:18Z / 3 年内更新 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM, .NET 8 |
| 领域 | 通用业务与交互 |
| 项目形态 | 业务应用 |
| 页面规模 | 微型（1～5 页）；实际 5 页 |
| 迁移挑战 | 外部 AI API、小样本 |
| 建议实验角色 | 主业务集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 57/0 | 57/0 |
| XML 成功/失败 | 38/0 | 38/0 |
| 页面/控件树 | 5/5 | 5/5 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.793 | 0.311 |

失败原因：基线与最终解析均通过。

相关解析器调整：多 csproj 资源合并

最终结论：**条件保留**。PDF 星标候选；简洁的对话式 WPF/MVVM 业务场景，MIT 许可

已知限制：最后推送为 2024 年；外部 AI API 未运行验证

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/SlimeNull/OpenGptChat.git repos/OpenGptChat
git -C repos/OpenGptChat fetch --depth 1 origin 754d5c4e41e31515f287fb53fb5a4e90621bee65
git -C repos/OpenGptChat sparse-checkout set -- OpenGptChat
git -C repos/OpenGptChat checkout --detach 754d5c4e41e31515f287fb53fb5a4e90621bee65
.venv/bin/python scripts/run_dataset_parse.py OpenGptChat --output-base-dir outputs/dataset-analysis/final
```

## 21. ModernFlyouts-Community/ModernFlyouts

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/ModernFlyouts-Community/ModernFlyouts |
| 来源 | PDF |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | ecf57081572b1b567c47c0f18aba78010e2fecb1 |
| 目标路径 | ModernFlyouts |
| Star / 提交数 | 4065 / 473 |
| 最后推送 / 活跃度 | 2024-11-17T02:39:02Z / 已归档 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, .NET Framework, Windows 系统集成 |
| 领域 | 桌面效率与系统集成 |
| 项目形态 | 业务应用 |
| 页面规模 | 小型（6～19 页）；实际 19 页 |
| 迁移挑战 | Windows Shell、已归档、自定义控件 |
| 建议实验角色 | 平台专项 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 72/0 | 72/0 |
| XML 成功/失败 | 32/0 | 32/0 |
| 页面/控件树 | 19/19 | 19/19 |
| 同名输出覆盖 | 2 | 0 |
| 耗时（秒） | 1.973 | 0.343 |

失败原因：基线在 C# 循环依赖处失败，优化后 19 个页面通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**条件保留**。现代 Windows Flyout 场景有补充价值；MIT 许可且页面数适中

已知限制：仓库已归档

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/ModernFlyouts-Community/ModernFlyouts.git repos/ModernFlyouts
git -C repos/ModernFlyouts fetch --depth 1 origin ecf57081572b1b567c47c0f18aba78010e2fecb1
git -C repos/ModernFlyouts sparse-checkout set -- ModernFlyouts
git -C repos/ModernFlyouts checkout --detach ecf57081572b1b567c47c0f18aba78010e2fecb1
.venv/bin/python scripts/run_dataset_parse.py ModernFlyouts --output-base-dir outputs/dataset-analysis/final
```

## 22. icsharpcode/ILSpy

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/icsharpcode/ILSpy |
| 来源 | PDF |
| PDF 星标 | 是 |
| 分析 ref | v9.1 |
| 固定 commit | 03b7444943e720b3134d296c0c8dd3876f8ea4ce |
| 目标路径 | ILSpy |
| Star / 提交数 | 25697 / 8035 |
| 最后推送 / 活跃度 | 2026-07-22T05:33:17Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM, .NET 8, 代码工具 |
| 领域 | 开发者工具 |
| 项目形态 | 业务应用 |
| 页面规模 | 中型（20～49 页）；实际 24 页 |
| 迁移挑战 | 复杂开发者工具、历史 WPF 版本、自定义控件 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | False | True |
| 失败阶段 | cs_dependency | 无 |
| C# 成功/失败 | 284/0 | 284/0 |
| XML 成功/失败 | 112/0 | 112/0 |
| 页面/控件树 | 24/24 | 24/24 |
| 同名输出覆盖 | 2 | 0 |
| 耗时（秒） | 481.381 | 2.373 |

失败原因：v9.1 基线在 C# 循环依赖处失败，优化后 24 个页面通过。

相关解析器调整：SCC 循环依赖压缩; 合并正则引用扫描

最终结论：**条件保留**。PDF 星标候选；高 star、MIT 许可的复杂开发者工具场景

已知限制：当前主分支已改用 Avalonia，因此固定在最后 WPF 版本 v9.1

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/icsharpcode/ILSpy.git repos/ILSpy
git -C repos/ILSpy fetch --depth 1 origin 03b7444943e720b3134d296c0c8dd3876f8ea4ce
git -C repos/ILSpy sparse-checkout set -- ILSpy
git -C repos/ILSpy checkout --detach 03b7444943e720b3134d296c0c8dd3876f8ea4ce
.venv/bin/python scripts/run_dataset_parse.py ILSpy --output-base-dir outputs/dataset-analysis/final
```

## 23. microsoft/WPF-Samples

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/microsoft/WPF-Samples |
| 来源 | GitHub 补充搜索 |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | ecd9529fb6941272eff1ee1e7e2554e3ecb2f1e4 |
| 目标路径 | Sample Applications/WPFGallery |
| Star / 提交数 | 5709 / 653 |
| 最后推送 / 活跃度 | 2026-07-15T02:23:02Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, CommunityToolkit.Mvvm, .NET 10, 控件 Gallery |
| 领域 | 控件与样式 Gallery |
| 项目形态 | 控件 Gallery |
| 页面规模 | 大型（50～99 页）；实际 73 页 |
| 迁移挑战 | Gallery、业务流程弱、自定义控件 |
| 建议实验角色 | 组件映射专项 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 145/0 | 145/0 |
| XML 成功/失败 | 77/0 | 77/0 |
| 页面/控件树 | 73/73 | 73/73 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.617 | 0.546 |

失败原因：补充候选的初次解析与最终解析均通过。

相关解析器调整：批量资源引用索引

最终结论：**保留**。Microsoft 官方、活跃、MIT 许可；补充 .NET 10 和现代 WPF 控件的 73 页面覆盖

已知限制：Gallery 偏控件演示，业务流程较弱

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/microsoft/WPF-Samples.git repos/WPF-Samples
git -C repos/WPF-Samples fetch --depth 1 origin ecd9529fb6941272eff1ee1e7e2554e3ecb2f1e4
git -C repos/WPF-Samples sparse-checkout set -- 'Sample Applications/WPFGallery'
git -C repos/WPF-Samples checkout --detach ecd9529fb6941272eff1ee1e7e2554e3ecb2f1e4
.venv/bin/python scripts/run_dataset_parse.py WPF-Samples --output-base-dir outputs/dataset-analysis/final
```

## 24. lepoco/wpfui

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/lepoco/wpfui |
| 来源 | GitHub 补充搜索 |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | ffebacd61058170cf63864b7d5aa730cffff848a |
| 目标路径 | src/Wpf.Ui.Gallery |
| Star / 提交数 | 9543 / 2137 |
| 最后推送 / 活跃度 | 2026-06-27T13:58:28Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, CommunityToolkit.Mvvm, .NET 10, Fluent UI Gallery |
| 领域 | 控件与样式 Gallery |
| 项目形态 | 控件 Gallery |
| 页面规模 | 大型（50～99 页）；实际 85 页 |
| 迁移挑战 | Gallery、第三方控件、样式密集 |
| 建议实验角色 | 组件映射专项 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 188/0 | 188/0 |
| XML 成功/失败 | 87/0 | 87/0 |
| 页面/控件树 | 85/85 | 85/85 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 0.557 | 0.503 |

失败原因：补充候选的初次解析与最终解析均通过。

相关解析器调整：批量资源引用索引

最终结论：**保留**。活跃、高 star、MIT 许可；补充 Fluent 自定义控件和现代 MVVM 页面覆盖

已知限制：Gallery 偏控件演示，自定义 Wpf.Ui 控件对后续 MUI 选择有额外压力

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/lepoco/wpfui.git repos/wpfui
git -C repos/wpfui fetch --depth 1 origin ffebacd61058170cf63864b7d5aa730cffff848a
git -C repos/wpfui sparse-checkout set -- src/Wpf.Ui.Gallery
git -C repos/wpfui checkout --detach ffebacd61058170cf63864b7d5aa730cffff848a
.venv/bin/python scripts/run_dataset_parse.py wpfui --output-base-dir outputs/dataset-analysis/final
```

## 25. BornToBeRoot/NETworkManager

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/BornToBeRoot/NETworkManager |
| 来源 | GitHub 补充搜索 |
| PDF 星标 | 否 |
| 分析 ref | main |
| 固定 commit | 1414181c76facdda647c2144c91360d7d04373f3 |
| 目标路径 | Source/NETworkManager |
| Star / 提交数 | 8491 / 4774 |
| 最后推送 / 活跃度 | 2026-07-20T23:09:32Z / 90 天内活跃 |
| 语言 / 许可证 | C# / GPL-3.0 |
| 技术栈 | WPF, MVVM, .NET 10, 网络管理 |
| 领域 | 网络与远程管理 |
| 项目形态 | 业务应用 |
| 页面规模 | 超大型（100 页及以上）；实际 125 页 |
| 迁移挑战 | 大规模、网络与系统能力、GPL-3.0 |
| 建议实验角色 | 压力集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 253/0 | 253/0 |
| XML 成功/失败 | 157/0 | 157/0 |
| 页面/控件树 | 125/125 | 125/125 |
| 同名输出覆盖 | 0 | 0 |
| 耗时（秒） | 3.471 | 3.612 |

失败原因：补充候选的初次解析与最终解析均通过。

相关解析器调整：生成目录过滤; 合并正则引用扫描; 批量资源引用索引

最终结论：**条件保留**。高 star、持续活跃的现代 WPF 业务应用；125 个页面且无同名覆盖，补充大型工具场景

已知限制：GPL-3.0 的后续分发需遵守相应义务；规模大，后续应分层取样

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/BornToBeRoot/NETworkManager.git repos/NETworkManager
git -C repos/NETworkManager fetch --depth 1 origin 1414181c76facdda647c2144c91360d7d04373f3
git -C repos/NETworkManager sparse-checkout set -- Source/NETworkManager
git -C repos/NETworkManager checkout --detach 1414181c76facdda647c2144c91360d7d04373f3
.venv/bin/python scripts/run_dataset_parse.py NETworkManager --output-base-dir outputs/dataset-analysis/final
```

## 26. TumblThreeApp/TumblThree

| 字段 | 内容 |
| --- | --- |
| URL | https://github.com/TumblThreeApp/TumblThree |
| 来源 | GitHub 补充搜索 |
| PDF 星标 | 否 |
| 分析 ref | master |
| 固定 commit | f108911025590bae3b34dbb912c35e26d69f49e1 |
| 目标路径 | src/TumblThree |
| Star / 提交数 | 728 / 1050 |
| 最后推送 / 活跃度 | 2026-07-11T23:08:31Z / 90 天内活跃 |
| 语言 / 许可证 | C# / MIT |
| 技术栈 | WPF, MVVM, .NET Framework, 下载管理 |
| 领域 | 文件与下载 |
| 项目形态 | 业务应用 |
| 页面规模 | 中型（20～49 页）；实际 20 页 |
| 迁移挑战 | 旧项目格式、下载队列、候选依赖多 |
| 建议实验角色 | 主业务集 |
| 克隆 | 成功；未执行候选仓库脚本或构建命令 |
| 克隆策略 | partial clone + sparse-checkout |

### 基线与复测

| 指标 | 基线 | 最终 |
| --- | --- | --- |
| 七阶段成功 | True | True |
| 失败阶段 | 无 | 无 |
| C# 成功/失败 | 327/0 | 327/0 |
| XML 成功/失败 | 33/0 | 33/0 |
| 页面/控件树 | 20/20 | 20/20 |
| 同名输出覆盖 | 2 | 0 |
| 耗时（秒） | 5.32 | 28.4 |

失败原因：补充候选的初次解析与最终解析均通过。

相关解析器调整：SCC 循环依赖压缩; 多 csproj 资源合并

最终结论：**条件保留**。活跃、MIT 许可的中型 MVVM 应用；补充下载队列与详情页场景

已知限制：使用较旧 .NET Framework 项目格式

复现命令：

```bash
git clone --filter=blob:none --no-checkout https://github.com/TumblThreeApp/TumblThree.git repos/TumblThree
git -C repos/TumblThree fetch --depth 1 origin f108911025590bae3b34dbb912c35e26d69f49e1
git -C repos/TumblThree sparse-checkout set -- src/TumblThree
git -C repos/TumblThree checkout --detach f108911025590bae3b34dbb912c35e26d69f49e1
.venv/bin/python scripts/run_dataset_parse.py TumblThree --output-base-dir outputs/dataset-analysis/final
```

## 27. 阶段一解析完整性

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
