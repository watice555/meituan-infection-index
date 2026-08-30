# 美团“传染病指数”接口抓取

这个目录负责从 iPhone 的美团 App 流量中定位“传染病指数”接口，并将最近 14 天曲线按日期累计到 SQLite 和 CSV。它不接入现有日报流水线，也不会自动发送或定时执行任何任务。

这是保留的旧抓包/重放工具。当前正式采集使用项目根目录的 `scripts/fetch_data.py`，无需 `dj-token` 或 iPhone；下面涉及 Token 的步骤只适用于旧工具，不是 GitHub Actions 的前置条件。

以下命令均在独立项目 `~/Projects_local/meituan-infection-index` 根目录运行，使用 Python 3.10+ 标准库，不再依赖日报项目的 `.venv`。

## 已确认的接口

```text
POST https://yiyao-h5.meituan.com/api/v1/health/marketingc/gateway/delivery/hawkeye/index
```

曲线位于：

```text
data.cityHealthDetailModule.diseaseSearchIndexList[].date
data.cityHealthDetailModule.diseaseSearchIndexList[].value
```

日期格式为 `YYYYMMDD`。响应中的 `diseaseStatusList` 会给出当前可用疾病及 `materialId`；脚本先取种子疾病，再自动发现和抓取其余疾病。

Mac 独立重放已经验证成功。Cookie、登录 Token、地址、用户 ID 和设备 UUID 均非必需；当前唯一需要保存在本地私有模板中的请求凭据是 `dj-token`。

## 安全边界

- `captures/` 和 `data/` 已被 Git 忽略；HAR 可能包含 Cookie、Token、设备标识和私人响应，不要提交或分享原文件。
- `data/request_template.json` 权限设为 `0600`，其中含 `dj-token`；不要复制到同步盘或提交到 Git。
- 不在仓库中保存 Proxyman CA、账户凭据或完整的 `Copy as cURL` 内容。
- 调试结束后，将 iPhone 当前 Wi-Fi 的 HTTP 代理恢复为“关闭”，并删除/取消信任 Proxyman CA。
- 若美团接口出现 TLS/SSL handshake error，而 Safari 的普通 HTTPS 流量可正常解密，则按 certificate pinning 处理，不继续绕过。

## 1. 查看当前抓包地址

先打开 Proxyman，然后运行：

```bash
python3 meituan_infection_index_capture/proxyman_capture.py status
```

脚本从 Proxyman CLI 动态读取当前 Mac 局域网 IP 和端口，不把易变的地址写死在仓库里。

## 2. 在 iPhone 上完成一次性设置

在 Proxyman 中打开：`证书 > 在 iOS 上安装证书 > 物理设备`，按窗口中的实时地址完成：

1. 在 Mac 上安装并信任本机生成的 Proxyman 根证书。
2. iPhone 与 Mac 连接同一 Wi-Fi；在该 Wi-Fi 的“配置代理”里选择“手动”，填写 Proxyman 显示的服务器和端口，关闭身份验证。
3. 用 iPhone Safari 隐私标签页打开 `http://proxy.man/ssl`，下载并安装 Proxyman CA。
4. 在 `设置 > 通用 > 关于本机 > 证书信任设置` 中开启对 Proxyman CA 的完全信任。

这几步会修改网络和证书信任设置，应只在本机受控网络中临时使用。

## 3. 抓取最小会话

在准备打开美团前清空当前 Proxyman 会话：

```bash
python3 meituan_infection_index_capture/proxyman_capture.py clear
```

随后只执行一次最小路径：打开美团，进入“传染病指数”，等待曲线完成加载，再在图上点若干数据点。不要在同一会话中打开支付、聊天或其他含私人信息的页面。

## 4. 导出并扫描候选接口

```bash
python3 meituan_infection_index_capture/proxyman_capture.py export
python3 meituan_infection_index_capture/inspect_har.py \
  meituan_infection_index_capture/captures/<导出的文件>.har \
  --report meituan_infection_index_capture/data/candidates.json
```

扫描器只把候选接口的 URL、状态码、JSON 路径和识别到的日期/数值点写入报告，不复制请求头、Cookie 或完整响应。优先查看高分候选，以及 URL/正文中含 `disease`、`infection`、`trend`、`chart`、`index`、`传染`、`指数` 等词的请求。

## 5. 从已解密 HAR 生成最小私有模板

```bash
python3 meituan_infection_index_capture/bootstrap_from_har.py \
  meituan_infection_index_capture/captures/<已解密文件>.har
```

提取器只保留 `dj-token`、通用网页头和非唯一业务参数；Cookie、登录态、地址、用户 ID、设备 UUID 等字段会被丢弃或置空。

## 6. 抓取全部疾病并累计

```bash
python3 meituan_infection_index_capture/fetch_indexes.py
```

默认产物：

```text
data/infection_index.sqlite3
data/infection_index.csv
```

SQLite 唯一键为 `(city_name, disease_id, date)`。每天重复抓取全部 14 天时，已存在日期会更新，以便保留美团对近期历史值的修订；新日期会追加。CSV 每次从 SQLite 全量重建，并使用 UTF-8 BOM 方便 Excel 打开。

如果返回 `dj-token 可能已过期`，重新走一次最小 Proxyman 会话并运行 `bootstrap_from_har.py`。这是预期的 Agent 异常恢复点；正常每日路径只运行 `fetch_indexes.py`。

## 7. 判断能否脱离 iPhone 重放

在 Proxyman 中对确认的单条请求使用 `Copy as cURL`，先在项目外的临时终端中重放。不要把带 Cookie/Token 的命令写入仓库或 shell 历史；可先手工删除不必要的标识头。

判断结果：

- 返回同样的 14 天 JSON：可以进入固定 Python 抓取、按日期 upsert 的阶段。
- 需要短期登录 Cookie/动态签名：先记录有效期和必需字段，再决定是否可稳定自动化。
- 美团请求 SSL handshake 失败，但 Safari HTTPS 解密正常：大概率是 pinning，停止接口路线，转 UI 自动化。

## 8. 清理

测试结束后务必：

1. 把 iPhone 当前 Wi-Fi 的“配置代理”改回“关闭”。
2. 在 iPhone 删除 Proxyman CA 配置描述文件并取消其完全信任。
3. 不再调试时退出 Proxyman。
