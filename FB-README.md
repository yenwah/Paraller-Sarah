# 📘 Facebook 爆款雷达(加在现有 IG 看板旁边)

和 IG 看板同一个仓库、同一个 Supabase、同一套「抓取 → AI 拆解 → 我的稿 → 看板」。
网址:`https://yenwah.github.io/Paraller-Sarah/fb.html`(IG 还是原来的首页,两边顶部有按钮可以切换)。

## 跟 IG 版不一样的地方

| | IG 看板 | FB 看板 |
|---|---|---|
| 抓谁 | `competitors` 表 `tracker = IG` | `competitors` 表 `tracker = FB`(专页) |
| 脚本 | `sync_content.py` | `sync_fb.py`(Apify 的 Facebook 专页 + 贴文抓取) |
| 「赞」 | 赞 | **所有表情回应的总数** |
| 多一个数字 | — | **转发数 Shares**(FB 最强的「想传出去」信号),可以按它排序 |
| 「我的稿」 | 30-60 秒口播稿 | **Facebook 贴文**(用 `brand_voice.md` 的语气和红线,不是口播) |
| 视频 | 抓下来转录口播 | FB 视频链接多半下载不了 → 主要靠文案拆解(FB 本来就是文字为主) |
| 筛选门槛 | ER ≥ 2% | ER ≥ 0.5%(FB 互动率天生比 IG 低) |
| 每周自动跑 | 周一 11:00 | 周一 11:30(错开) |

工作台 `team.html` 的「拍摄中」队列现在 IG 和 FB 合在一起,每条带 IG/FB 小标。

## 安装(全程网页点鼠标,约 10 分钟)

**第 1 步 · Supabase(一次)**
Supabase → SQL Editor → 把 `fb-setup.sql` 整段贴进去 → Run。
它做两件事:给 `posts` 加 `shares` 列;把 16 个同行(马来西亚 + 新加坡)放进 `competitors`,`tracker = FB`。
只有 *Sigi Skin* 默认没勾(FB 显示店面曾关闭)。名单来自 `同行研究-2026-11-11.md`,**专页还没逐个打开核对过**,第一次跑完看日志表,抓到 0 条的专页就是名字不对。

**第 2 步 · 上传文件到 GitHub 仓库**
仓库首页 → Add file → Upload files,把下面的文件拖进去(同名会直接替换),Commit changes:

- 新增:`sync_fb.py`、`fb-setup.sql`、`FB-README.md`、`.github/workflows/sync-fb.yml`
- 替换:`generate_dashboard.py`、`analyze_posts.py`、`rewrite_posts.py`、`.github/workflows/analyze.yml`

> `.github/workflows/` 里的文件在网页上传时要先进到那个文件夹再上传(或用 Add file → Create new file,文件名打 `.github/workflows/sync-fb.yml` 再把内容贴进去)。

**第 3 步 · 第一次运行**
Actions → **Sync Facebook** → Run workflow。跑完会自动接力:AI 拆解 → 我的稿 → 生成网页(约 10-30 分钟)。
然后打开 `fb.html`。不需要新的钥匙,用的还是 `APIFY_TOKEN` / `GEMINI_API_KEY` 等现有 Secrets。

## 第一次跑完,先看这个

Actions → Sync Facebook → 日志里的**逐个专页表格**:

- `抓到` 是 0 → 专页名对不上或专页不公开,去 `competitors` 表改 Username(只要 facebook.com/ 后面那一段)
- 有「对不上专页」→ 日志里 `[Debug]` 那两行是 Apify 回传的字段名,把它贴给我,我对一下字段
- 有「缺粉丝数」→ 同上,多半是网址问题

> ⚠️ Apify 的 Facebook 抓取器字段名我是按它的公开文档写的,**还没有用你的账号真跑过**。脚本已经对几种常见字段名做了兜底,但第一次跑请看一眼日志。

## 内容太少 / 想调松(不用改代码)

仓库 Settings → Secrets and variables → Actions → **Variables** 加(全部可选):

| Variable | 默认 | 作用 |
|---|---|---|
| `FB_MIN_ER` | `0.005` | 互动率门槛(0.5%) |
| `FB_MIN_COMMENTS` | `8` | 评论数门槛 |
| `FB_MIN_ENGAGE` | `10` | 噪音底线(回应+评论太少的丢掉) |
| `FB_OUTLIER_X` | `1.5` | 超出该专页自己中位数多少倍算爆 |
| `FB_TOP_N_PER_COMP` | `3` | 每个专页保底几条 |
| `FB_MAX_PER_COMP` | `15` | 每个专页最多几条 |
| `FB_DAYS_BACK` | `90` | 回看几天(不额外花钱) |
| `FB_RESULTS_LIMIT` | `30` | 每个专页抓几条(**这个才会加 Apify 账单**) |

## 费用

沿用你现有的 Apify 额度。16 个专页 × 30 条 = 每周约 480 条贴文,每月大概是 IG 那一份的量级;实际金额以 Apify 的 Billing 页面为准(我没有查到准确单价,不乱报数字)。想省钱:把 `FB_RESULTS_LIMIT` 调到 15,或先把标杆大号(Cetaphil、Physiogel)取消勾。

## 怎么用在「不知道发什么」上

- 先点 **按 Shares 排序**:被转发最多的 = 别人觉得「值得传给朋友」的题材,最适合拿来想选题。
- 点卡片上的 **我的稿**:AI 已经把这条改写成你语气的 FB 贴文(带你的红线:不写几天见效、不写没证据的数字)。**先给你看,不要直接发。**
- 把「拍摄中」当成「我这周要发的选题」。
