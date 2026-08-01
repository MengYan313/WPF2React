# 迁移模块

本模块消费 `outputs/<project>/` 的解析与依赖产物，按“资源 → C# → 数据 → 页面”顺序编排 Agent，最终把 React/TypeScript 文件写入 `results/<project>/`。MUI 检索语料仅作为生成上下文，不改变 Parser 的中间合同。

`MigrationOrchestrator` 只持有一个 `MigrationTeam`，团队内所有生成式 Agent 共享同一份 `llm_config`，Runtime 按顶层请求创建并在请求结束后统一关闭。JSON 响应由共享流程严格校验并最多修复一次；修复失败直接传播。批量 C#、数据和页面迁移只在单文件、单资源或单页面边界隔离失败，不在 Agent 处理器中重复吞噬异常。

## 启动命令

```bash
.venv/bin/python -m src.migration ExpenseItDemo

# 正式数据集按冻结页面集合运行；项目级资源、C#、数据阶段仍保留完整上下文
.venv/bin/python -m src.migration Prism \
  --output-base-dir outputs/parser-completeness/after-run-2 \
  --page-set docs/research/experiment-page-set-v2.json
```

运行前必须先完成 Parser，并配置 `.env`。迁移会把源码上下文发送到模型端点，应事先确认成本与披露范围。

架构和数据流见[仓库架构](../../docs/guides/repository-architecture.md)。Baseline 与评价分别见 [baselines/README.md](baselines/README.md) 和 [evaluation/README.md](evaluation/README.md)。

离线验证：

```bash
.venv/bin/python -m unittest tests.migration.test_orchestration -v
```
