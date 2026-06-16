# Xiaohongshu Codex Workflows

## 团队使用说明

### 这个项目是什么

这是一个小红书内容运营生产流水线，用来把热帖素材整理成热帖分析、三账号文案、图片包、发布前清单和微信日报。

它不是自动发帖系统，不做无人值守发布，不做点赞、评论、关注、收藏、养号，也不做平台风控规避。最终发布动作必须人工确认。

### 员工日常怎么用

1. 把当天要导入的热帖文本放到 `inputs/hotposts-import.txt`。
2. 运行：

```bash
npm run daily
```

3. 查看三账号发布包：

```text
outputs/latest/role-publish-ready.md
```

4. 查看图片文件：

```text
outputs/latest/visual-images/
```

5. 查看微信日报：

```text
outputs/latest/wechat-daily-digest.txt
```

### 测试怎么跑

```bash
npm run demo
```

`demo` 用于团队试跑，不依赖飞书、Apify、微信推送等外部服务。

### 全流程调试怎么跑

```bash
npm run full
```

`full` 会跑完整采集、生产和交付链路，适合排查数据源、推送和输出文件。

### 输出在哪里

- `outputs/latest/`：最新一次运行结果，员工日常优先看这里。
- `outputs/runs/`：历史运行归档，每次运行会按 Run ID 单独保存。
- `outputs/controller-status.md`：兼容旧入口的状态文件。
- `outputs/latest/controller-status.md`：最新一次运行的状态文件。

### 常见问题

- 如果报错，先看 `outputs/latest/controller-status.md`。
- 如果没有生成图片，看 `outputs/latest/visual-package.md` 和 `outputs/latest/visual-images/manifest.json`。
- 如果文案不对，优先检查 `configs/accounts/` 和 `knowledge/sop-rules.json`。
- 如果热帖分析为空，检查 `inputs/hotposts-import.txt` 或 `inputs/hotposts.json`。

## 云端自动运行

### GitHub Actions 用途

GitHub Actions 用于每天自动运行：

```bash
npm run daily
```

它只做内容生产、发布包整理、图片包生成和日报产出，不是小红书自动发帖系统，不会自动点赞、评论、关注、收藏或养号。

### 配置步骤

1. 把项目推到 GitHub 仓库。
2. 在 GitHub Repository Settings 里配置 Secrets，例如 WxPusher、飞书、企业微信 webhook、Apify 等需要的 token/key。
3. 确认 `.github/workflows/xhs-daily.yml` 存在。
4. 进入 GitHub Actions 页面，手动运行一次 `workflow_dispatch`。
5. 在 workflow artifact 里下载并查看 `outputs/latest`。

### 日常产物

- `outputs/latest/`：最新结果。
- `outputs/runs/`：历史归档。
- `controller-status.md`：运行状态。
- `wechat-daily-digest.txt`：日报。
- `role-publish-ready.md`：发布包。
- `visual-images/`：图片包。

### 注意事项

- GitHub Actions 是内容生产自动化，不是小红书自动发布。
- 不要在仓库里提交 `.env.local`。
- 不要把 webhook、token、key 写进代码。
- 如果 workflow 失败，先看 artifact 里的 `controller-status.md` 和 `cloud-check-status.md`。
- `.github/workflows/xhs-daily.yml` 里的 cron 使用 UTC 时间；如果要按中国时间或日本时间运行，需要手动换算，例如北京时间 09:00 对应 UTC 01:00。

这个项目给你一个可持续扩展的小红书运营工作流底座，优先解决 3 件事：

1. 热帖分析整理
2. 按模版生成发帖草稿
3. 三账号内容节奏、发布队列和账号健康运营清单

## 当前边界

- 支持本地整理和生成工作流
- 支持按关键词生成小红书爆帖采集计划
- 支持接入 Apify Xiaohongshu Search Scraper，把近期搜索结果合并进热帖库
- 支持把分析结果整理成统一结构，方便后续喂给 Codex
- 支持按学生号、IP号、业务号生成不同口吻的发帖草稿
- 支持按上游词、中游词、下游词做搜索覆盖复盘
- 支持自动生成待发布包，整理标题、正文、封面思路、标签、检查项和计划发布时间
- 支持生成微信日报摘要，方便发送到微信后在手机确认
- 不包含规避平台规则、批量刷行为、伪装账号活跃等违规自动化
- 不无人值守发布内容到小红书；最终发布动作需要人工确认

## 目录结构

- `knowledge/sop-rules.json`
  SOP 规则库，包含账号角色、搜索漏斗、内容模型和合规边界
- `inputs/hotposts.json`
  你手工收集的热帖样本
- `inputs/collect-keywords.json`
  每日自动采集关注的关键词池
- `inputs/external-hotposts.json`
  外部合规数据源导出的热帖 JSON，会自动合并进热帖库
- `inputs/hotpost-inbox/`
  自动收集 inbox，适合持续放入小红书复制文本、Markdown、JSON 导出文件
- `/Users/meilucia/Downloads/社媒助手/`
  社媒助手导出的表格目录，支持 Excel/CSV 自动筛选爆款
- `inputs/hotposts-import.txt`
  文本导入入口，适合粘贴可见页面、第三方表格或人工整理结果
- `inputs/post-brief.json`
  你要发的内容简报
- `inputs/publish-queue.json`
  待发布队列，包含账号、计划发布时间、标题、正文来源、封面思路和标签
- `outputs/`
  脚本生成结果
- `prompts/`
  给 Codex 继续深化分析或改稿时使用的提示词
- `templates/`
  标准分析模版、通用发帖模版、三账号发帖模版
- `topic-library/three-account-topic-matrix.md`
  学生号、IP号、业务号的选题矩阵

## 使用方式

### 自动跑

一次性跑完整套流程：

```bash
npm run all
```

现在 `npm run all` 会调用总控工作流 `npm run control`，并生成：

- `outputs/controller-status.md`
- `outputs/controller-status.json`

总控会分组执行采集、分析、生产和交付步骤；可选步骤失败或关闭时会显示为跳过，不会把整条链路变成黑盒。

持续监听输入文件，修改后自动重跑：

```bash
npm run auto
```

适合接系统定时任务的命令：

```bash
npm run daily
```

Codex 里已经创建了一个每日自动任务：每天 09:00 自动运行完整工作流，并更新 `outputs/`。

本地持续自动跑的方式：

1. 打开终端
2. 进入项目目录
3. 运行 `npm run auto`
4. 后续只要修改 `inputs/hotposts.json` 或 `inputs/post-brief.json`，系统会自动重跑

注意：`npm run auto` 需要终端保持打开；每日 Codex 自动任务不需要你一直开着这个监听命令。

### 0. 生成爆帖采集计划

编辑 `inputs/collect-keywords.json`，配置每天要看的关键词，然后运行：

```bash
npm run collect
```

输出文件：

- `outputs/collection-plan.md`
- `outputs/collection-status.json`

Chrome 自动读取小红书页面需要 Codex Chrome Extension 正常安装并启用，且你已在 Chrome 里正常登录小红书。遇到验证码、登录或权限弹窗时需要人工处理。

当前实测状态：

- Chrome 可以打开小红书搜索页。
- Codex Chrome Extension 可以连接 Chrome。
- 小红书搜索页 DOM 读取会超时，不适合直接作为每日无人值守采集方式。
- 公共 HTML 初始状态没有稳定返回搜索结果 feed。
- 已预留 `npm run collect:visual` 做截图视觉采集，但本机暂缺稳定 OCR 环境。

因此当前每日自动任务会先生成采集计划；真正把页面结果自动写入 `hotposts.json`，需要先补齐 OCR 或稳定页面数据源。

### 0.1 接入合规数据源或文本导入

如果你有外部合规来源导出的热帖数据，把数组 JSON 放入：

```bash
inputs/external-hotposts.json
```

然后运行：

```bash
npm run collect:source
```

也可以设置自己的 JSON 接口：

```bash
XHS_SOURCE_URL="https://你的数据接口/items.json" npm run collect:source
```

每日自动任务建议把地址写入 `.env.local`：

```text
XHS_SOURCE_URL=https://你的数据接口/items.json
```

如果只是临时导入，把文本放入：

```bash
inputs/hotposts-import.txt
```

支持单行格式：

```text
标题 | 作者 | 点赞 | 评论 | 收藏 | 长尾词
```

或者文本块格式：

```text
标题
作者：xxx
点赞：123
评论：45
收藏：67
关键词：KCL AI率 essay
```

然后运行：

```bash
npm run collect:import
```

### 0.2 从社媒助手表格提取爆款

把社媒助手导出的 `.xlsx` 或 `.csv` 表格放进：

```bash
/Users/meilucia/Downloads/社媒助手/
```

然后运行：

```bash
npm run collect:social
```

脚本会递归扫描表格，读取这些列：

- `笔记标题`
- `笔记内容`
- `笔记链接`
- `点赞量`
- `收藏量`
- `评论量`
- `分享量`
- `博主昵称`

默认筛选规则：

- 热度分：`点赞 + 收藏*1.5 + 评论*2 + 分享*1.2`
- 单个表格最多取前 30 条
- 优先保留总互动不低于 50 的内容
- 如果某个表没有达到门槛的内容，会取该表热度分最高的内容，避免空跑

可在 `.env.local` 调整：

```text
SOCIAL_ASSISTANT_DIR=/Users/meilucia/Downloads/社媒助手
SOCIAL_ASSISTANT_MIN_TOTAL=50
SOCIAL_ASSISTANT_MAX_PER_FILE=30
```

输出文件：

- `outputs/collection-social-assistant-status.md`
- `outputs/collection-social-assistant-status.json`
- `inputs/hotposts.json`

`npm run control` 和 `npm run all` 已经包含这一步，所以每日总控会自动从社媒助手表格里提取爆款。

### 0.3 自动收集爆帖 Inbox

如果你想让系统每天自动“吃进”新爆帖样本，把 `.txt`、`.md` 或 `.json` 文件放进：

```bash
inputs/hotpost-inbox/
```

然后运行：

```bash
npm run collect:inbox
```

支持常见复制格式：

```text
标题：英国留学申请避坑
链接：https://www.xiaohongshu.com/explore/xxxx
点赞：1288
收藏：456
评论：89
正文：这篇讲申请时间线和材料准备。
```

也支持 JSON 数组或 `{ "items": [...] }`。脚本会自动解析、标准化、去重合并到 `inputs/hotposts.json`，并生成：

- `outputs/collection-inbox-status.md`
- `outputs/collection-inbox-status.json`

`npm run control` 和 `npm run all` 已经包含这一步，所以每日总控会自动扫描 inbox。

`npm run all` 已经包含 `collect:source`、`collect:social`、`collect:inbox`、`collect:import`、`collect:api` 和 `collect:apify`。能采集到的数据会去重合并到 `inputs/hotposts.json`，再进入分析、草稿、发布包和微信日报。

### 0.4 接入 Apify 小红书搜索采集器

如果你要落地“自动搜索近期爆款”，推荐优先使用第三方数据源，不直接让本机浏览器硬读小红书页面。项目已接入 Apify 的 Xiaohongshu Search Scraper：

```bash
npm run collect:apify
```

首次使用需要在项目根目录新建 `.env.local`，填入：

```text
APIFY_TOKEN=你的 Apify token
XHS_COOKIE=你在浏览器登录小红书后的 cookie_val
APIFY_XHS_ACTOR_ID=kuaima/xiaohongshu-search
```

关键词仍然从 `inputs/collect-keywords.json` 读取：

```json
{
  "dailyLimitPerKeyword": 5,
  "keywords": [
    {
      "keyword": "KCL AI率 essay",
      "accountRoleHint": "ip",
      "searchFunnelHint": "midstream"
    }
  ]
}
```

输出文件：

- `outputs/collection-apify-status.md`
- `outputs/collection-apify-status.json`
- `inputs/hotposts.json`

如果没有配置 `APIFY_TOKEN` 或 `XHS_COOKIE`，脚本会自动跳过，不会打断 `npm run all`。如果采集成功，数据会按标题/链接去重合并进 `inputs/hotposts.json`。

注意：Apify 采集属于第三方数据源调用，使用前请确认你的账号、cookie、采集范围和频率符合平台规则与业务风险边界。本项目只做搜索结果整理，不做发布、点赞、评论、关注、收藏或任何规避风控动作。

### 1. 整理热帖分析

编辑 `inputs/hotposts.json`，填入你观察到的热帖样本，然后运行：

```bash
npm run analyze
```

输出文件：

- `outputs/hotpost-analysis.md`
- `outputs/hotpost-analysis.json`

建议每条样本都补充：

- `accountRole`：`student`、`ip`、`business`
- `searchFunnel`：`upstream`、`midstream`、`downstream`
- `longTailKeyword`：学生会真实搜索的长尾词
- `commentTrigger`：能引发真实评论的问题

### 2. 生成发帖草稿

编辑 `inputs/post-brief.json`，运行：

```bash
npm run draft
```

输出文件：

- `outputs/post-draft.md`

### 3. 生成账号健康运营清单

```bash
npm run ops
```

输出文件：

- `outputs/account-ops-checklist.md`

### 4. 生成待发布包

编辑 `inputs/publish-queue.json`，运行：

```bash
npm run publish
```

输出文件：

- `outputs/publish-ready.md`
- `outputs/publish-queue-status.json`

`publish-ready.md` 会把待发布内容整理成可检查格式。最终发布到小红书前，需要人工确认标题、正文、图片、标签和账号无误。

### 5. 生成微信日报摘要

```bash
npm run wechat
```

输出文件：

- `outputs/wechat-daily-digest.txt`
- `outputs/wechat-daily-digest.md`

`wechat-daily-digest.txt` 适合发送到微信，手机上快速确认当天待发布内容。发送到微信属于对外传输信息，自动发送前需要确认目标会话。

### 6. 每日自动推送到微信

个人微信没有稳定的官方无人值守发送接口，不建议用窗口点击脚本做自动发送。推荐使用企业微信群机器人 webhook。

配置环境变量后运行：

```bash
WECHAT_WEBHOOK_URL="你的企业微信群机器人webhook" npm run push:wechat
```

每日自动任务建议把 webhook 写入 `.env.local`：

```text
WECHAT_WEBHOOK_URL=你的企业微信群机器人webhook
```

`npm run all` 已经包含这一步。没有配置 `WECHAT_WEBHOOK_URL` 时会自动跳过推送，并写入：

- `outputs/wechat-push-status.json`

配置好 webhook 后，每日 09:00 自动任务会生成内容并推送到对应微信群。

### 7. 使用 WxPusher 推送到微信

如果不想用企业微信，可以使用 WxPusher。先在 `.env.local` 填入：

```text
WXPUSHER_TOKEN=你的 WxPusher appToken
WXPUSHER_UID=你的 WxPusher UID
```

然后运行：

```bash
npm run push:wxpusher
```

脚本会读取最新的 `outputs/wechat-daily-*.txt`，格式化为 HTML 后调用 WxPusher：

```text
POST https://wxpusher.zjiecode.com/api/send/message
```

如果没有配置 `WXPUSHER_TOKEN` 或 `WXPUSHER_UID`，脚本会安全跳过，并写入：

- `outputs/wxpusher-push-status.json`

### 8. 使用飞书自建应用推送

如果要把每日待确认内容推送到飞书，在 `.env.local` 填入：

```text
LARK_APP_ID=你的飞书 App ID
LARK_APP_SECRET=你的飞书 App Secret
LARK_RECEIVE_ID_TYPE=chat_id
LARK_RECEIVE_ID=接收人或群聊 ID
```

然后运行：

```bash
npm run push:lark
```

脚本会读取最新的 `outputs/wechat-daily-*.txt`，先获取 `tenant_access_token`，再调用飞书消息接口发送文本消息。如果没有配置完整，会安全跳过，并写入：

- `outputs/lark-push-status.json`

如果希望 `npm run all` / `npm run control` 每天自动推送飞书，把 `.env.local` 中的开关打开：

```text
XHS_AUTO_PUSH_LARK=true
```

### 9. 从飞书表格读取素材

如果你把小红书爆款、选题或素材整理在飞书电子表格里，可以让每日工作流自动读取。先在 `.env.local` 填入：

```text
LARK_APP_ID=你的飞书 App ID
LARK_APP_SECRET=你的飞书 App Secret
LARK_SHEET_URLS=https://你的飞书表格链接
LARK_SHEET_RANGE=A1:Z300
```

然后运行：

```bash
npm run collect:lark
```

脚本会读取表格第一行作为表头，识别常见字段：`标题`、`内容`、`链接`、`点赞`、`收藏`、`评论`、`关键词`、`账号类型` 等，并合并到：

- `inputs/hotposts.json`
- `outputs/collection-lark-sheets-status.json`
- `outputs/collection-lark-sheets-status.md`

如果表格里是课程作业信息，也会自动识别：`学校`、`课程代码`、`课程名称`、`评估方式`、`占比`、`DDL`、`交付物`、`rubric/评分标准`、`学生需求/卡点`、`官网链接`。这些内容会写入：

- `inputs/course-context.json`
- `outputs/course-context-bank.json`

后续 `npm run draft:roles` 会自动把课程代码、作业类型、DDL、评分点写进学生号/IP号/业务号草稿和配图方向里。

如果要专门生成“按课程作业发精细化”的草稿，运行：

```bash
npm run draft:courses
```

输出文件：

- `outputs/course-precision-post-drafts.md`
- `outputs/course-precision-post-drafts.json`

这个文件会按每门课分别生成学生号、IP号、业务号草稿，适合用来做课程代码 + 作业类型 + DDL + 评分点的长尾搜索内容。

如果有多个表格，`LARK_SHEET_URLS` 可以用英文逗号分隔。更精细的配置可以使用：

```text
LARK_FILE_SOURCES_JSON=[{"name":"学生号素材","url":"https://...","range":"A1:Z300","accountRole":"student"}]
```

如果飞书 API 权限还没打通，也可以先用导出文件跑通精细化生产链：从飞书把表格导出为 `.xlsx` 或 `.csv`，放到：

```text
inputs/lark-course-sheets/
```

然后运行：

```bash
npm run collect:lark
npm run draft:courses
```

## 推荐工作流

### 每天

1. 更新 `inputs/collect-keywords.json`，放入今天要看的搜索词。
2. 跑 `npm run all`。
3. 查看 `outputs/collection-apify-status.md` 和 `outputs/hotpost-analysis.md`。
4. 查看 `outputs/post-draft.md`，人工改稿。
5. 查看 `outputs/publish-ready.md`，人工确认后再去小红书创作者后台发布。
6. 如配置了企业微信群机器人，查看 `outputs/wechat-push-status.json` 确认日报推送状态。

### 只跑爆款搜索

```bash
npm run collect:apify
npm run analyze
```

### 只生成待发布包

```bash
npm run draft
npm run publish
```

发布前仍然需要人工确认标题、正文、图片、标签和账号无误。

## 三账号规则

- 学生号：只做真实日常、焦虑、吐槽、求助，不提服务。
- IP号：做过程分享、经验复盘和温度化解释。
- 业务号：做课程难点、案例复盘、风险拆解和搜索承接。

## 搜索漏斗

- 上游词：刚开始焦虑，还没明确解决方案。
- 中游词：已经知道问题，在找怎么办和方法。
- 下游词：准备比较方案、评估可信度、看案例结果。

## 后续可继续接入

- 浏览器采集脚本
- 稳定 OCR 整理
- 合规第三方数据源/API
- 定时自动汇总
- 选题库管理
- 多模版文案实验
