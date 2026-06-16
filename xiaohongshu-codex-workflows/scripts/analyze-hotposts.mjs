import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const inputPath = path.join(root, "inputs", "hotposts.json");
const rulesPath = path.join(root, "knowledge", "sop-rules.json");
const outputJsonPath = path.join(root, "outputs", "hotpost-analysis.json");
const outputMdPath = path.join(root, "outputs", "hotpost-analysis.md");

const posts = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const rules = JSON.parse(fs.readFileSync(rulesPath, "utf8"));

if (!Array.isArray(posts) || posts.length === 0) {
  throw new Error("inputs/hotposts.json 不能为空。");
}

const average = (values) =>
  Math.round(values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length);

const topHooks = [...new Set(posts.map((post) => post.hook).filter(Boolean))];
const topCTAs = [...new Set(posts.map((post) => post.cta).filter(Boolean))];
const tones = [...new Set(posts.flatMap((post) => post.tone || []).filter(Boolean))];
const structures = [...new Set(posts.flatMap((post) => post.structure || []).filter(Boolean))];
const accountRoles = [...new Set(posts.map((post) => post.accountRole).filter(Boolean))];
const searchFunnels = [...new Set(posts.map((post) => post.searchFunnel).filter(Boolean))];
const longTailKeywords = [...new Set(posts.map((post) => post.longTailKeyword).filter(Boolean))];

const formatRole = (role) => rules.accountRoles[role]?.name || role || "未填写";
const formatFunnel = (funnel) => rules.searchFunnels[funnel]?.name || funnel || "未填写";

const summary = {
  sampleSize: posts.length,
  avgLikes: average(posts.map((post) => post.likes)),
  avgComments: average(posts.map((post) => post.comments)),
  avgFavorites: average(posts.map((post) => post.favorites)),
  repeatedHooks: topHooks,
  repeatedCTAs: topCTAs,
  repeatedTones: tones,
  repeatedStructures: structures,
  accountRoles,
  searchFunnels,
  longTailKeywords
};

const insights = [
  `账号角色覆盖：${accountRoles.map(formatRole).join("、") || "暂无"}`,
  `搜索阶段覆盖：${searchFunnels.map(formatFunnel).join("、") || "暂无"}`,
  `长尾词样本：${longTailKeywords.join("；") || "暂无"}`,
  `高频开头钩子集中在：${topHooks.join("；") || "暂无"}`,
  `高频语气特征集中在：${tones.join("、") || "暂无"}`,
  `高频内容结构集中在：${structures.join("；") || "暂无"}`,
  `高频结尾动作集中在：${topCTAs.join("；") || "暂无"}`
];

const report = {
  summary,
  insights,
  posts: posts.map((post, index) => ({
    index: index + 1,
    title: post.title,
    accountRole: post.accountRole || "",
    accountRoleName: formatRole(post.accountRole),
    searchFunnel: post.searchFunnel || "",
    searchFunnelName: formatFunnel(post.searchFunnel),
    topic: post.topic,
    audience: post.audience,
    longTailKeyword: post.longTailKeyword || "",
    hook: post.hook,
    structure: post.structure || [],
    tone: post.tone || [],
    commentTrigger: post.commentTrigger || "",
    cta: post.cta || "",
    notes: post.notes || ""
  }))
};

const markdown = [
  "# 热帖分析报告",
  "",
  "## 总览",
  "",
  `- 样本数：${summary.sampleSize}`,
  `- 平均点赞：${summary.avgLikes}`,
  `- 平均评论：${summary.avgComments}`,
  `- 平均收藏：${summary.avgFavorites}`,
  `- 账号角色覆盖：${summary.accountRoles.map(formatRole).join("、") || "暂无"}`,
  `- 搜索阶段覆盖：${summary.searchFunnels.map(formatFunnel).join("、") || "暂无"}`,
  "",
  "## 共性结论",
  "",
  ...insights.map((item) => `- ${item}`),
  "",
  "## 单条拆解",
  "",
  ...report.posts.flatMap((post) => [
    `### ${post.index}. ${post.title}`,
    "",
    `- 账号角色：${post.accountRoleName}`,
    `- 搜索阶段：${post.searchFunnelName}`,
    `- 赛道：${post.topic || "未填写"}`,
    `- 受众：${post.audience || "未填写"}`,
    `- 长尾词：${post.longTailKeyword || "未填写"}`,
    `- 开头钩子：${post.hook || "未填写"}`,
    `- 语气：${post.tone.join("、") || "未填写"}`,
    `- 评论触发点：${post.commentTrigger || "未填写"}`,
    `- CTA：${post.cta || "未填写"}`,
    `- 结构：${post.structure.join("；") || "未填写"}`,
    `- 备注：${post.notes || "无"}`,
    ""
  ]),
  "## SOP 规则提醒",
  "",
  ...rules.platformLogic.map((item) => `- ${item}`),
  `- 推荐内容结构：${rules.contentModel.recommended}`,
  "",
  "## 合规边界",
  "",
  ...rules.complianceBoundaries.map((item) => `- ${item}`),
  "",
  "## 下一步建议",
  "",
  "- 先补齐上游、中游、下游三个阶段的样本，不要只看单一爆帖。",
  "- 每条内容都标注账号角色，避免学生号、IP号、业务号语气混用。",
  "- 每次只测试一个变量，比如长尾词、首图信息密度或评论区开放问题。"
].join("\n");

fs.mkdirSync(path.dirname(outputJsonPath), { recursive: true });
fs.writeFileSync(outputJsonPath, JSON.stringify(report, null, 2));
fs.writeFileSync(outputMdPath, markdown);

console.log(`已生成 ${outputJsonPath}`);
console.log(`已生成 ${outputMdPath}`);
