# Daily

Daily 是一个 AI 驱动的公开信息情报流。V1 聚焦中国经济，只接入国家统计局，将公开资料自动抓取、去重、聚合为经济事件，提取可追溯指标，再生成精选信息流和每日经济摘要。

它不是新闻搬运站。项目首先回答：今天真正发生了什么、哪些变化值得关注、与此前相比有什么不同。

## 当前能力

- 国家统计局“数据发布 / 数据解读 / 最新发布和解读”列表与详情抓取
- Channel、Document、EconomicEvent、Metric 通用数据模型
- 宏观总览、官方解读和发布会聚合为一个经济事件
- 工业、消费、投资、民间投资、房地产、就业、CPI、PPI、外贸、服务业和能源指标提取
- 本地历史序列、变化方向、透明经济评分、精选和热点
- DeepSeek 结构化分析、JSON Schema 校验、失败重试、哈希缓存与无密钥降级
- 精选、全部动态、热点、日报、指标、详情、关于和前端本地搜索
- GitHub Actions 每日自动更新和 GitHub Pages 独立部署

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
SITE_BASE_URL=/ .venv/bin/daily pipeline --no-ai --max-documents 10
.venv/bin/python scripts/serve.py
```

打开 `http://127.0.0.1:8000/`。构建 GitHub Pages 版本时使用默认的 `/daily/` base path：

```bash
.venv/bin/daily build
```

指定页面做真实抓取：

```bash
.venv/bin/daily pipeline --no-ai --url 'https://www.stats.gov.cn/sj/zxfb/202608/t20260817_1965056.html'
```

重复运行是幂等的：Document 使用规范 URL 稳定标识，正文哈希参与去重；Event 使用统计期稳定标识；DeepSeek 只分析内容未命中缓存的事件。

## 配置与 Secrets

复制 `.env.example` 中需要的值到本地环境，或在 GitHub 仓库 Settings → Secrets and variables → Actions 配置：

- `DEEPSEEK_API_KEY`：可选；缺失时仅跳过 AI，抓取和网站仍工作。
- `DEEPSEEK_MODEL`：推荐设置为仓库 Variable，默认 `deepseek-chat`。
- `SITE_BASE_URL`：Pages 固定为 `/daily/`，本地预览可设为 `/`。

Telegram 的 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 和 `ENABLE_TELEGRAM` 已预留，但 V1 不发送消息。任何密钥都不得提交到 Git、生成数据或前端。

## 数据可信性

事实、官方解释和 AI 分析分层展示。指标保留 `source_document` 和 `source_text`；没有发布时间时 `publish_time` 保持 `null`；历史比较只读取 `data/metrics/series.json`。AI 不得补造数字，资金流向无明确证据时必须留空或标记为推测。

数据按稳定 ID 或日期保存在 `data/`，网站产物在 `site-output/`（不提交）。每次运行的抓取或分析错误记录在 `data/logs/YYYY-MM-DD.json`，单页或 AI 失败不会阻止其余网站生成。

## GitHub Pages 设置

1. 创建公开仓库 `Miles-ya/daily` 并推送 `main`。
2. 在 Settings → Pages → Build and deployment 中选择 **GitHub Actions**。
3. 在 Actions 中手动运行一次 **Daily pipeline**。
4. 成功后 **Deploy Pages** 自动发布到 `https://miles-ya.github.io/daily/`。

定时任务使用 `15 23 * * *`（UTC），即北京时间每天 07:15。数据先提交到仓库，再由独立部署工作流发布，因此部署失败不会丢失抓取数据。

## 测试

测试使用保存的国家统计局风格 HTML fixture，覆盖 URL 规范化、去重、分类、事件合并、指标来源、历史比较、评分、AI 降级与 Schema，以及 `/daily/` 资源路径。正式验收还会真实请求国家统计局页面；网络问题应被记录而不伪装成成功。

## 下一阶段

1. 扩充国家统计局页面变体和指标规则的回归样本。
2. 接入中国政府网、国家发改委、财政部和中国人民银行。
3. 增加 Telegram Digest 的实际发送、状态去重和失败重试。
4. 在积累足够历史序列后增加克制的趋势图表与异常检测。
