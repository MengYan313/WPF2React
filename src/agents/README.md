# Agent 基础模块

本模块提供两个项目统一的 `BaseRoutedAgent`、默认 `AgentId` 和注册函数。WPF 迁移领域 Agent 位于 `src/migration/`，本模块不保存领域提示词或迁移策略。

该模块没有独立运行入口。离线验证命令：

```bash
.venv/bin/python -m unittest discover -s tests/agents -t . -v
```

Agent 生命周期和消息路由约定见[两项目共享开发约定](../../docs/guides/shared-development-conventions.md)。
