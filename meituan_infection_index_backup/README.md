# 美团指数本地备份

这个目录把已经发布到 GitHub Pages 的美团指数下载到本地，并累计保存为 SQLite 和 CSV。它不需要 `dj-token`、iPhone 或 Proxyman。

默认备份内容：

```text
data/infection_index.sqlite3
data/infection_index.csv
data/last_sync.json
```

SQLite 使用 `(city_id, disease_id, date)` 作为唯一键。每次同步会更新美团修订过的近期数值、追加新日期，但不会删除已经在本地保存的旧日期。CSV 每次从 SQLite 全量重建，使用 UTF-8 BOM，方便 Excel 打开。

在独立项目 `~/Projects_local/meituan-infection-index` 根目录手动同步：

```bash
python3 meituan_infection_index_backup/backup.py
```

## 本机定时同步

这台 Mac 使用系统自带的 `launchd`，每天 11:00 直接执行 `sync_meituan_index.sh`。它不依赖 Codex。任务定义保存在本机的：

```text
~/Library/LaunchAgents/local.meituan-infection-index.backup.plist
```

现有任务的 `ProgramArguments` 指向本项目的 `meituan_infection_index_backup/sync_meituan_index.sh`，`WorkingDirectory` 指向独立项目根目录。脚本按自身位置定位备份目录，不再写死日报项目路径。以后移动项目时，仍需更新 LaunchAgent 中的绝对路径并重新加载；本仓库不会自动安装新的定时任务。

查看状态或手动触发：

```bash
launchctl print "gui/$(id -u)/local.meituan-infection-index.backup"
launchctl kickstart -k "gui/$(id -u)/local.meituan-infection-index.backup"
```

运行日志保存在 `data/logs/`，仍属于被 Git 忽略的本地数据。Mac 在计划时间睡眠时，`launchd` 会在唤醒后补运行一次；Mac 长期关机时不会在云端执行。

离线校验：

```bash
python3 -m unittest discover -s meituan_infection_index_backup/tests -v
python3 -m py_compile meituan_infection_index_backup/backup.py
```

`data/` 是本地运行产物，已被 Git 忽略。源码、测试和说明由 Git 管理，实际备份数据不会提交到仓库。
