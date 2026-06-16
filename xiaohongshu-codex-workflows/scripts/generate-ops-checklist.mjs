import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const rulesPath = path.join(root, "knowledge", "sop-rules.json");
const outputPath = path.join(root, "outputs", "account-ops-checklist.md");
const rules = JSON.parse(fs.readFileSync(rulesPath, "utf8"));

const markdown = [
  "# 账号健康运营清单",
  "",
  "## 核心原则",
  "",
  ...rules.platformLogic.map((item) => `- ${item}`),
  `- 推荐内容结构：${rules.contentModel.recommended}`,
  "",
  "## 日常",
  "",
  "- 检查当天内容是否标注账号角色：学生号、IP号或业务号。",
  "- 检查当天内容是否标注搜索阶段：上游词、中游词或下游词。",
  "- 检查标题是否包含具体场景、情绪和结果导向的长尾词。",
  "- 查看最近评论区，优先回复真实问题和高意图互动。",
  "- 记录标题、长尾词、账号角色、发布时间、赞藏评和私信量。",
  "- 收集评论区高频原话，为下一篇内容补选题。",
  "",
  "## 三账号分工",
  "",
  `- 学生号：${rules.accountRoles.student.job}`,
  `- IP号：${rules.accountRoles.ip.job}`,
  `- 业务号：${rules.accountRoles.business.job}`,
  "",
  "## 每周",
  "",
  "- 每个搜索阶段至少补 2 个样本：上游情绪、中游方法、下游案例。",
  "- 复盘高表现内容，判断是长尾词、首图、内容角色还是评论问题有效。",
  "- 统计哪些内容带来收藏，哪些内容带来真实评论。",
  "- 检查三账号语气是否有明显差异，避免内容看起来像同一个模板。",
  "- 整理 5 到 10 条同行热帖，补充到热帖分析样本中。",
  "",
  "## 每月",
  "",
  "- 找出当月互动最高的 3 篇内容，拆成长尾词、结构、评论问题和配图四个资产。",
  "- 清理重复度高但转化低的选题，避免账号疲劳。",
  "- 评估评论和私信里的真实需求，决定下个月的课程代码和任务类型覆盖。",
  "- 把高频课程代码沉淀为专题内容矩阵。",
  "",
  "## 注意事项",
  "",
  ...rules.complianceBoundaries.map((item) => `- ${item}`),
  "- 更稳妥的增长方式是提高选题命中率、内容可收藏性和评论质量。"
].join("\n");

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, markdown);

console.log(`已生成 ${outputPath}`);
