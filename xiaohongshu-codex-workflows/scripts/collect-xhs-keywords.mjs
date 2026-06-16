import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const configPath = path.join(root, "inputs", "collect-keywords.json");
const outputPath = path.join(root, "outputs", "collection-plan.md");
const statusPath = path.join(root, "outputs", "collection-status.json");

const config = JSON.parse(fs.readFileSync(configPath, "utf8"));

const keywords = Array.isArray(config.keywords) ? config.keywords : [];
const xhsSearchUrl = (keyword) =>
  `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}`;

const status = {
  generatedAt: new Date().toISOString(),
  mode: config.mode || "chrome_assisted",
  platform: config.platform || "xiaohongshu",
  keywordCount: keywords.length,
  note: "当前脚本生成每日采集计划和搜索入口。页面读取需要 Codex Chrome Extension 可用，且不处理登录、验证码或反爬规避。"
};

const markdown = [
  "# 小红书爆帖采集计划",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  "",
  "## 今日关键词",
  "",
  ...keywords.flatMap((item, index) => [
    `### ${index + 1}. ${item.keyword}`,
    "",
    `- 搜索入口：${xhsSearchUrl(item.keyword)}`,
    `- 建议采集数量：${config.dailyLimitPerKeyword || 5}`,
    `- 账号角色提示：${item.accountRoleHint || "未填写"}`,
    `- 搜索阶段提示：${item.searchFunnelHint || "未填写"}`,
    `- 备注：${item.notes || "无"}`,
    "",
    "采集字段：标题、链接、作者类型、点赞、收藏、评论、正文摘要、评论区高频问题、账号角色、搜索阶段、长尾词。",
    ""
  ]),
  "## Chrome 自动采集说明",
  "",
  "- 需要 Codex Chrome Extension 正常安装并启用。",
  "- 需要你已在 Chrome 中正常登录小红书。",
  "- 遇到验证码、登录、权限弹窗时停止，交给你处理。",
  "- 不做反爬规避、批量互动、点赞、收藏、评论或关注。",
  "",
  "## 当前输出",
  "",
  "- 这个文件先生成每日采集入口。",
  "- Chrome 可用后，采集结果会写入 `inputs/hotposts.json`，再进入 `npm run analyze`。"
].join("\n");

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, markdown);
fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));

console.log(`已生成 ${outputPath}`);
console.log(`已生成 ${statusPath}`);
