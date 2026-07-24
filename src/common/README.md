# 公共基础设施

本模块提供统一日志、源码身份、兼容模型配置导出和进度条封装，不包含解析或迁移算法。业务代码统一通过 `get_logger()` 同时写入控制台和 `logs/<run-name>.log`。

该模块没有独立业务入口。验证命令：

```bash
.venv/bin/python -m unittest tests.common.test_shared_infrastructure -v
.venv/bin/python scripts/check_shared_infrastructure.py --other ../CodeIdiomMine
```

共享边界见[两项目共享开发约定](../../docs/guides/shared-development-conventions.md)。
