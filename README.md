# 意欧晨报

意大利 / 欧洲中文新闻、天气地图、米兰活动、夜店、街舞、米兰房价和特价机票，每天米兰时间 6:45 自动更新。

网页是纯静态文件（`index.html` + `data/*.json` + `geo/*.json`），托管在 GitHub Pages 上。每天的内容由 Claude 云端定时任务「意欧晨报每日更新」生成：它运行 `pipeline/` 里的脚本抓取数据、挑选并编译新闻，然后把新的 `data/` 文件提交到本仓库的 `claude/site` 分支，GitHub Pages 自动发布。

## 目录

| 路径 | 内容 |
|---|---|
| `index.html` | 网页本身 |
| `data/latest.json` | 天气、米兰活动、夜店、街舞、更新状态 |
| `data/<日期>.json` | 当天新闻（保留 7 天） |
| `data/market.json` | 米兰房价、特价机票 |
| `geo/` | 意大利、欧洲、世界、米兰街区地图 |
| `pipeline/collect.py` | 抓取候选新闻、天气、罢工、活动、夜店、街舞日历 |
| `pipeline/article.py` | 抓取选中新闻的正文和配图 |
| `pipeline/market.py` | 抓取米兰房源、瑞安航空 / Wizz Air / Google Flights 机票 |
| `pipeline/build.py` | 把挑选结果生成为 `data/` 下的 JSON |
| `每日任务指令.txt` | 云端定时任务的指令全文 |

## 绑定自己的域名

1. 在域名注册商的 DNS 设置里加一条记录（以子域名 `yiou.example.com` 为例）：
   - 类型 `CNAME`，主机 `yiou`，值 `<你的 GitHub 用户名>.github.io`
   - 如果用根域名（`example.com`），改加 4 条 `A` 记录，值分别是 `185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`
2. 打开仓库 Settings → Pages → Custom domain，填入 `yiou.example.com`，保存。
3. 等 DNS 生效（几分钟到几小时），勾选 **Enforce HTTPS**。

## 手动更新一次

在 https://claude.ai/code/routines 找到「意欧晨报每日更新」，点 Run now。
