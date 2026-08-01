# WPF 迁移实验页面集合

当前机器可读页集是 [`experiment-page-set.json`](experiment-page-set.json)。它覆盖 20 个正式项目中的 73 个页面、688 个控件实例和 35 条集合内页面边。

## 选择原则

1. 只从阶段一成功解析的页面中选择，不读取迁移结果和评价分数。
2. 页面结构必须完整，输入输出、绑定或事件合同能够从当前源码理解。
3. 排除占位页、动态内容空壳、平台宿主页和前后端边界不清晰的伪简单页面。
4. 同时保留有真实页面关系的联动页和少量低复杂度独立页。
5. 主方法、baseline 和评价必须使用同一个文件作为分母。

当前集合包含 52 个参与页面关系的页面和 21 个独立页面，其中 20 个独立页不超过 10 个控件。人工登记的边保留源码路径、行号和片段作为证据。

## 生成展开结果

```bash
.venv/bin/python scripts/build_experiment_page_set.py \
  --spec docs/research/experiment-page-set.json \
  --parser-root outputs/parser-completeness/current \
  --output results/dataset/experiment-page-set.json
```

页集发生变化时直接更新当前文件，并让所有方法统一重跑。不得根据迁移结果只替换失败页面。
