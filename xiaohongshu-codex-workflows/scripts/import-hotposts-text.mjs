import fs from "node:fs";
import path from "node:path";
import { mergeHotposts, normalizeHotpost, readJsonArray, toNumber } from "./hotpost-utils.mjs";

const root = path.resolve(process.cwd());
const importPath = path.join(root, "inputs", "hotposts-import.txt");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const statusPath = path.join(root, "outputs", "collection-import-status.json");
const reportPath = path.join(root, "outputs", "collection-import-status.md");

const text = fs.existsSync(importPath) ? fs.readFileSync(importPath, "utf8").trim() : "";

const parseLinePost = (line) => {
  const parts = line
    .split(/[|\t]/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (parts.length < 2) return null;

  const [title, author = "", likes = 0, comments = 0, favorites = 0, keyword = ""] = parts;
  return normalizeHotpost({
    title,
    authorType: author,
    likes: toNumber(likes),
    comments: toNumber(comments),
    favorites: toNumber(favorites),
    longTailKeyword: keyword || title,
    topic: keyword || title,
    notes: "由 hotposts-import.txt 文本导入。"
  });
};

const parseBlockPost = (block) => {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return null;

  const item = { title: lines[0] };
  for (const line of lines.slice(1)) {
    const match = line.match(/^([^:：]+)[:：]\s*(.+)$/);
    if (!match) continue;
    const key = match[1].trim().toLowerCase();
    const value = match[2].trim();
    if (["author", "作者", "账号"].includes(key)) item.authorType = value;
    if (["likes", "点赞", "赞"].includes(key)) item.likes = value;
    if (["comments", "评论"].includes(key)) item.comments = value;
    if (["favorites", "收藏"].includes(key)) item.favorites = value;
    if (["keyword", "关键词", "长尾词"].includes(key)) item.longTailKeyword = value;
    if (["url", "链接"].includes(key)) item.url = value;
    if (["role", "账号角色"].includes(key)) item.accountRole = value;
    if (["funnel", "搜索阶段"].includes(key)) item.searchFunnel = value;
  }

  return normalizeHotpost(item, {
    notes: "由 hotposts-import.txt 文本块导入。"
  });
};

let parsed = [];
if (text) {
  const blocks = text.split(/\n\s*\n/g).map((block) => block.trim()).filter(Boolean);
  parsed = blocks
    .map((block) => {
      if (block.includes("|") || block.includes("\t")) return parseLinePost(block.split("\n")[0]);
      return parseBlockPost(block);
    })
    .filter(Boolean);
}

const mergeResult = parsed.length
  ? mergeHotposts(hotpostsPath, parsed)
  : { total: readJsonArray(hotpostsPath).length, added: 0 };

const status = {
  generatedAt: new Date().toISOString(),
  importPath,
  parsedCount: parsed.length,
  addedCount: mergeResult.added,
  hotpostsTotal: mergeResult.total,
  format: "每行格式：标题 | 作者 | 点赞 | 评论 | 收藏 | 长尾词；或使用空行分隔文本块。"
};

const report = [
  "# 文本热帖导入状态",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `解析数量：${parsed.length}`,
  `新增合并：${mergeResult.added}`,
  `热帖库总数：${mergeResult.total}`,
  "",
  "## 支持格式",
  "",
  "```text",
  "标题 | 作者 | 点赞 | 评论 | 收藏 | 长尾词",
  "```",
  "",
  "或：",
  "",
  "```text",
  "标题",
  "作者：xxx",
  "点赞：123",
  "评论：45",
  "收藏：67",
  "关键词：KCL AI率 essay",
  "```"
].join("\n");

fs.mkdirSync(path.dirname(statusPath), { recursive: true });
fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
fs.writeFileSync(reportPath, report);

console.log(`已生成 ${statusPath}`);
console.log(`已生成 ${reportPath}`);
console.log(`文本导入新增 ${mergeResult.added} 条，热帖库共 ${mergeResult.total} 条。`);
