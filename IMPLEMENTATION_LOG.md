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

## 独立项目迁移

- 阶段总结：
  - 先快进同步原网页仓库至 `f702e77`，保留已有无 Token 采集修复，再将仓库连同 `.git` 移至同级 `meituan-infection-index/`，保留远程、分支、历史与 Git 配置。
  - 从日报仓库 `f05b51f` 提取抓包与本地备份工具、测试和说明；原有工具历史仍留在原仓库，未将日报的其他源码、配置或历史导入公开仓库。
  - 搬移现有运行数据和私有抓包，强化 Git 忽略规则；Pages 改为仅打包网页和公开城市数据，并将两组工具测试加入工作流。
  - 备份入口按自身位置定位目录；更新并重载已有 LaunchAgent 的绝对路径，保留每天 11:00 的计划，不手动触发。
  - 补充独立项目说明和工作约定，明确旧 Token 抓包工具不再是正式采集的前置条件。
- 已执行的验证：
  - 搬移时核对全部 123 个文件的 SHA-256 与权限；随后再次确认 74 个运行数据/抓包文件原样保留且被 Git 忽略，两份 SQLite 的 `integrity_check` 均为 `ok`。
  - Homebrew Python 执行站点 15 项、旧抓包 8 项、备份 4 项测试全部通过；系统 Python 另通过站点 15 项和备份 4 项，确认本机任务使用的解释器可用。
  - Python 编译、JavaScript 与 zsh 语法检查、工作流 YAML 与所有内联 shell 语法检查均通过；候选提交未包含真实私有模板凭据或运行产物。
  - 离线 fixture 验证实际 Pages 整理步骤不会复制抓包、备份、私有配置或非公开旁路文件；备份脚本在带空格的新位置、无关工作目录下能够正确定位、记录日志并传递成功/失败退出码。
  - 对照迁移前配置确认 GitHub 计划、权限、并发组及部署环境未变；只读确认远程 Pages、Actions、Secret 名称和变量状态，未读取 Secret 值。
  - LaunchAgent 已加载新路径，计划仍为 11:00，迁移后运行次数为 0。原日报使用其既有虚拟环境通过 38 项回归测试及编译；最初用系统 PATH 中无 PyYAML 的解释器导入失败，切换到项目既有环境后通过，未安装或变更依赖。
  - 未执行真实采集、备份下载或手动云端部署；本阶段验证使用离线测试与 fixture。旧抓包测试在 Python 3.14 下出现现有 SQLite 连接清理 ResourceWarning，但测试结果通过，未扩大修改范围。
- 时间戳：2026-08-31 03:34:53 Asia/Shanghai
- 写入者模型：未知（运行环境未暴露）
- 设备：TianhaodeMacBook-Pro.local（macOS 26.6.2，arm64）
