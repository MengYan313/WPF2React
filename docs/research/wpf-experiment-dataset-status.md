# WPF 实验数据集现状

当前正式数据集包含 20 个公开 WPF 项目。项目需具有可确认的 XAML + C# 源码、可用许可证和可识别的工程定义；解析成功只表示当前静态分析器可处理，不表示项目能够完整构建或迁移正确。

项目按实际用途覆盖框架样例、业务应用、控件 Gallery、开发者工具、媒体、网络、文件管理和桌面系统集成等场景。复杂项目用于压力与专项分析，低复杂度项目用于快速冒烟验证。

机器可读清单由 `scripts/build_dataset_manifest.py` 写入 `results/dataset/dataset-manifest.json`，当前统计由 `scripts/analyze_dataset_stats.py` 写入 `results/dataset/dataset-statistics.json`。

正式页面实验统一使用 [`experiment-page-set.json`](experiment-page-set.json)：73 个页面、688 个控件和 35 条集合内页面边。选择规则见[WPF 迁移实验页面集合](experiment-page-set.md)。
