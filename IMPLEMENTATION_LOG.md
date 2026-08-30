# Implementation Log

## 无 Token 抓取与更新可靠性

- 阶段总结：移除 `MEITUAN_DJ_TOKEN` 和 `dj-token` 请求头依赖，清理请求体中的空 token 字段；为网络超时、HTTP 429/5xx 和临时 `code=-1` 响应增加有限重试，为抓取进度及最终错误补充城市与素材上下文；同步更新 GitHub Actions、测试和 README。
- 已执行的验证：
  - 使用无 token 请求完整抓取并合并 56 城、280 条疾病序列，生成 7,000 个历史数据点；所有序列最新日期均为 `2026-08-29`。生成数据位于临时目录，未纳入 Git 提交。
  - 使用系统 Python 3.9.6 执行 `python3 -m unittest discover -s tests -v`，15 项测试全部通过。
  - 使用 Homebrew Python 3.14.6 执行 `/opt/homebrew/bin/python3 -m unittest discover -s tests -v`，15 项测试全部通过。
  - 使用两个 Python 版本分别执行 `py_compile`，并执行 `node --check app.js` 与 `git diff --check`，均通过。
- 时间戳：2026-08-30 12:40 Asia/Shanghai
- 写入者模型：未知（运行环境未暴露）
- 设备：MacBook Pro（macOS 26.6.2，arm64）
