# 本地运行基线

当前工作区使用项目根目录 `.venv` 和 Python 3.11。依赖安装入口是 `requirements.txt`；`requirements-local.lock` 仅保留在本机并由 Git 忽略。

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -t . -v
```

阶段一结果写入 `outputs/<project>/`，迁移结果写入 `results/<project>/`。正式页面实验只读取 `docs/research/experiment-page-set.json`，阶段一全量产物默认位于 `outputs/parser-completeness/current`。

本文不保存旧提交、旧页集、前后版本比较或产物摘要。新的运行事实由当前测试和脚本直接生成。
