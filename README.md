# 政策雷达

政策雷达持续监测少数中央政策源，把新文件解析成可搜索的公开政策流，并将结合个人情况的行动判断私发到 Telegram。网站不再按“日报”组织：有新政策就增加一条，没有更新就保持现状。

## 工作方式

- 每天北京时间 08:07–18:07，每小时扫描一次。
- 关注产业方向、资金流向、创业机会、就业与城市、宏观环境。
- 监测中国政府网、国家发展改革委、财政部、中国人民银行、住房城乡建设部、工业和信息化部、国家网信办、科技部、商务部等官方来源。
- 同一文件的不同部门转载会按文号或标题合并，并保留镜像链接。
- 网站只展示政策事实、公共解析、证据和不确定性。
- Telegram 才展示“对我意味着什么”“所以我该干什么”等个性化判断。

AI 不可用时，抓取和网站仍会运行，政策先标记为“待完整分析”；后续轮次会自动补做分析。直接来源故障会写入运行日志，不会伪装成成功。

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest

# 真实扫描，不调用 AI
SITE_BASE_URL=/ .venv/bin/daily policy --no-ai

# 只用已有数据重建网站
SITE_BASE_URL=/ .venv/bin/daily policy-build

# 本地预览
.venv/bin/python scripts/serve.py
```

打开 `http://127.0.0.1:8000/`。GitHub Pages 使用 `/daily/` 作为基础路径。

常用命令：

```bash
# 不访问网络，用本地记录补分析并重建
.venv/bin/daily policy --offline

# 对指定政策执行 Telegram 通知
ENABLE_TELEGRAM=true .venv/bin/daily policy-notify \
  --policy-ids "policy-id-1,policy-id-2" \
  --site-url "https://miles-ya.github.io/daily/"
```

旧的经济日报命令仍保留为兼容入口，但不再用于自动任务。

## GitHub 配置

在仓库 Settings → Secrets and variables → Actions 添加：

- Secret `DEEPSEEK_API_KEY`：公共政策解析和私人简报。
- Secret `TELEGRAM_BOT_TOKEN`：Telegram BotFather 生成的机器人令牌。
- Secret `TELEGRAM_CHAT_ID`：接收私信的 chat ID。
- Secret `PERSONAL_PROFILE_JSON`：只参与私人简报生成，不写入仓库、日志或网站。
- Variable `DEEPSEEK_BASE_URL`：可选，默认 `https://api.b.ai/v1/chat/completions`。
- Variable `DEEPSEEK_MODEL`：可选，默认 `deepseek-v4-flash`。

`PERSONAL_PROFILE_JSON` 示例：

```json
{
  "identity": "学生",
  "horizon": "未来 1-3 年",
  "priorities": ["挣钱", "就业", "创业", "城市选择", "行业判断"],
  "cities": ["深圳", "杭州", "上海"]
}
```

在 Settings → Pages 中选择 **GitHub Actions**，然后手动运行一次 **Policy monitor**。此后工作流会按北京时间每小时运行：先更新公开数据并发布 Pages，部署成功后再发送私人 Telegram 简报。通知账本只保存政策 ID 和内容哈希，用于防止重复推送。

## 数据与隐私边界

- `data/policies/`：官方原文、来源和元数据。
- `data/policy_assessments/`：可公开的结构化政策解析。
- `data/policy_ai_cache/`：可公开分析的 AI 缓存。
- `data/policy_logs/`：每轮发现数、变化和错误。
- `data/notifications/telegram.json`：不含消息正文的发送账本。
- `site-output/`：静态网站产物，不提交。

私人画像只从 GitHub Secret 注入。私人简报使用临时缓存，在进程结束时删除；代码不会把画像或 Telegram 正文写入上述目录。

## 测试

```bash
.venv/bin/pytest
SITE_BASE_URL=/daily/ .venv/bin/daily policy-build
git diff --check
```

测试覆盖政策筛选、主题识别、重要性评分、官方页面解析、公开站点结构和隐私隔离。
