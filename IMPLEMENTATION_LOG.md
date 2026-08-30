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

## GitHub Pages 生产更新验证

- 阶段总结：将无 token 抓取改动推送至 `main`，手动触发“更新并发布指数”工作流，并完成生产数据与页面部署验证。
- 已执行的验证：
  - GitHub Actions 运行 `33293065985` 在提交 `644e4b7` 上成功完成；56 城抓取、离线校验、产物上传及 Pages 部署均通过。
  - 线上 `data/manifest.json` 已更新至 `2026-08-30T04:50:32+00:00`，包含 56 城、280 条序列和 7,000 个数据点。
  - 线上杭州城市分片包含 5 条序列、125 个历史数据点，所有序列最新日期均为 `2026-08-29`。
- 时间戳：2026-08-30 12:51 Asia/Shanghai
- 写入者模型：未知（运行环境未暴露）
- 设备：MacBook Pro（macOS 26.6.2，arm64）
