# 城市传染病指数

一个非官方的美团 App“传染病指数”历史查询站。页面完全静态，发布在 GitHub Pages；GitHub Actions 每天抓取五个已验证城市的最近 14 天数据，与已发布历史合并后重新发布。

站点地址：<https://watice555.github.io/meituan-infection-index/>

## 当前范围

- 城市：杭州、上海、北京、深圳、广州
- 指数：过敏、新冠、急性胃肠炎、甲流、肺炎支原体感染
- 数据：美团 App 页面公开展示的搜索指数，仅用于趋势观察，不是疾病病例数，也不构成医疗建议

## 安全设计

- `dj-token` 只保存在仓库的 GitHub Actions Secret `MEITUAN_DJ_TOKEN` 中。
- Token 不写入源码、日志、网页数据或 Git 提交。
- 发布数据只包含城市、疾病、日期和指数等页面展示信息。
- 抓取失败时不部署，保留上一版可用站点和历史数据。
- 公开仓库连续 60 天无活动时 GitHub 可能停用定时工作流；定时任务最多每 30 天创建一次不含文件变化的保活提交，避免每日更新被静默停用。

## 本地验证

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/fetch_data.py
node --check app.js
```

本地预览需要先生成 `data/indexes.json`，再在本目录启动任意静态 HTTP 服务。直接双击 `index.html` 会受到浏览器本地文件读取限制。
