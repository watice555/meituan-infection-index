# 城市传染病指数

一个非官方的美团 App“传染病指数”历史查询站。页面完全静态，发布在 GitHub Pages；GitHub Actions 每天抓取 56 个可用城市的最近 14 天数据，与已发布历史合并后重新发布。

站点地址：[美团指数存档](https://watice555.github.io/meituan-infection-index/)

本项目现独立放在 `~/Projects_local/meituan-infection-index`，不依赖 `daily_report` 的代码、虚拟环境或配置。

## 项目结构

- `index.html`、`app.js`、`styles.css`：静态查询页面。
- `scripts/`、`config/`、`tests/`：正式无 Token 采集、历史恢复、公开请求模板及离线测试。
- `scripts/import_hangzhou_history.py`：从本地 xlsx 的“杭州”工作表提取新冠、甲流和支原体手工历史；读取单元格底层数值，避免错误数字格式把指数误判为日期。
- `.github/workflows/pages.yml`：GitHub Actions 定时采集和 Pages 部署。
- `meituan_infection_index_backup/`：从已发布站点累计本地 SQLite/CSV 备份，参见[备份说明](meituan_infection_index_backup/README.md)。
- `meituan_infection_index_capture/`：保留的 Proxyman 抓包与旧接口调试工具，参见[抓取说明](meituan_infection_index_capture/README.md)；当前正式采集不需要它。
- `data/` 及工具目录下的 `data/`、`captures/`：本机运行产物，不提交 Git。

## GitHub 与本机任务

- 沿用现有 [GitHub 仓库](https://github.com/watice555/meituan-infection-index) 和 `main` 分支，保留完整网页仓库历史；移动本地目录不改变仓库、Pages 地址或仓库设置。
- Pages 的构建来源为 GitHub Actions，部署环境为 `github-pages`，保持 HTTPS。
- 云端采集继续使用每日 `00:20 UTC`（北京时间 `08:20`）计划，实际启动时间可能延迟，也可在 GitHub Actions 页面手动运行。
- 工作流权限仍为 `contents: write`、`pages: write`、`id-token: write`，用于保活提交和 Pages 部署；正式采集不需要配置 Secret。
- Pages 产物仅包含网页文件、`data/manifest.json` 和 `data/cities/*.json`；抓包、备份、脚本及本地配置不进入站点发布包。
- 本机已有 LaunchAgent 继续在每天 `11:00` 备份，入口已迁至本项目。新克隆不会自动安装或启动定时任务。

## 当前范围

- 城市：美团页面可用的 56 个城市
- 指数：过敏、新冠、急性胃肠炎、甲流、肺炎支原体感染
- 数据：美团 App 页面公开展示的搜索指数，仅用于趋势观察，不是疾病病例数，也不构成医疗建议

## 安全设计

- 抓取当前公开页面展示的指数无需登录或 `dj-token`，工作流不保存、读取或发送美团账号凭据。
- 请求模板会主动移除遗留的 `dj-token` 请求头，避免过期凭据导致整批抓取失败。
- 发布数据只包含城市、疾病、日期和指数等页面展示信息。
- 网络超时、HTTP 429/5xx 和接口临时返回 `code=-1` 时会有限重试；失败日志会标出城市 ID 和指数素材 ID。
- 抓取失败时不部署，保留上一版可用站点和历史数据。
- 公开数据按城市拆分；页面只下载城市清单和当前选择城市的数据文件。
- 历史缺失日期不插值。趋势图按真实日历时间定位，并在缺口处断线；图下显示记录天数、缺失天数和连续数据段数。
- 手工杭州历史的数据点带有 `manual_hangzhou_xlsx` 来源标记，页面表格、提示和 CSV 导出显示“手工历史”；后续自动采集在日期重叠时优先。
- 公开仓库连续 60 天无活动时 GitHub 可能停用定时工作流；定时任务最多每 30 天创建一次不含文件变化的保活提交，避免每日更新被静默停用。

## 本地验证

在项目根目录运行以下命令。工具仅使用 Python 标准库；完整测试需 Python 3.10+（旧 HAR 扫描器使用 `zip(strict=True)`），JavaScript 语法检查需要 Node.js，无需安装日报项目的依赖。

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s meituan_infection_index_capture/tests -v
python3 -m unittest discover -s meituan_infection_index_backup/tests -v
python3 -m py_compile scripts/fetch_data.py scripts/restore_history.py scripts/import_hangzhou_history.py
python3 -m compileall -q meituan_infection_index_capture meituan_infection_index_backup
node --check app.js
zsh -n meituan_infection_index_backup/sync_meituan_index.sh
```

## 杭州手工历史

本地 xlsx 和生成的种子文件属于运行数据，不提交 Git。先归档原始工作簿，再生成可重复导入的种子并合并到本地站点数据：

```bash
mkdir -p meituan_infection_index_backup/data/manual_sources
cp -p ~/Downloads/美团指数.xlsx meituan_infection_index_backup/data/manual_sources/杭州美团指数.xlsx
python3 scripts/import_hangzhou_history.py \
  --xlsx meituan_infection_index_backup/data/manual_sources/杭州美团指数.xlsx \
  --seed-output meituan_infection_index_backup/data/manual_hangzhou_history.json \
  --data-dir data
```

GitHub Actions 可从仓库变量 `HANGZHOU_HISTORY_GZIP_BASE64` 读取 gzip 后的种子 JSON。变量未配置时工作流行为不变；配置后，种子先与已发布历史合并，再由当天自动采集覆盖重叠日期。首次发布成功后，手工历史也会被下一次工作流从已发布站点恢复。种子值只包含公开的城市、病种、日期、指数和来源标记，不含账号或请求凭据。

本地预览需要先生成 `data/manifest.json` 和 `data/cities/*.json`，再在本目录启动任意静态 HTTP 服务。直接双击 `index.html` 会受到浏览器本地文件读取限制。
