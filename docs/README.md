# 文档索引

根目录只保留项目入口 `README.md` 和开发契约 `AGENTS.md`；其余项目自有文档统一归档在 `docs/`。项目自有文档使用中文，代码、命令、路径和必要技术标识保留英文；`rags/` 中的第三方 MUI 检索语料保持来源语言。

## 开发文档

- [两项目共享开发约定](guides/shared-development-conventions.md)：与 CodeIdiomMine 一致的日志、LLM、AutoGen、目录和测试契约。
- [提示词优化本地指南](guides/prompt-engineering-guide.md)：日常提示词结构、JSON 契约、验证流程与官方指南刷新条件。
- [依赖说明](guides/dependencies.md)：Python、AutoGen、解析和可选检索依赖。
- [本地开发基线](guides/local-baseline.md)：已验证环境、测试结果与当前阻塞。
- [迁移评价指标规范](guides/evaluation-metrics.md)：工程可用性与用户可见质量两层指标的分类、公式、价值和边界。
- [分层迁移评测使用指南](guides/evaluation.md)：GT 清单、编译/调用测试、截图对、CLI 和 JSON 输出配置。
- [UI 迁移 baseline 设计与运行规范](guides/baselines.md)：三条 baseline 的方法边界、预算、产物、公平性、命令和验证证据。
- [Git 工作流](guides/git-workflow.md)：仓库提交和推送约定。

## 研究文档

- [前端 UI 迁移研究稿](research/02_前端UI迁移研究稿.md)
- [面向代码可复用性增强的融合研究方案](research/03_面向代码可复用性增强的融合研究方案.md)
- [WPF 实验数据集现状统计](research/wpf-experiment-dataset-status.md)：候选分布、筛选结果、解析器优化前后及最终数据集概况。
- [WPF 实验数据集逐项排查记录](research/wpf-experiment-dataset-audit.md)：每个候选的固定提交、解析证据、限制和复现命令。

研究稿是未来实验背景，不替代当前源码、`AGENTS.md` 和已验证基线。

两份研究稿引用了 `docs/references/英文文献库.md` 和 `docs/references/中文文献库.md`，但这两个文献库不在当前仓库中。现阶段保留原引用并明确记录缺失状态，不伪造参考文献内容；补入正式文献库后再统一验证锚点。
