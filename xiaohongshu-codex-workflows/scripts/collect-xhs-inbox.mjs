import fs from "node:fs";
import path from "node:path";
import { mergeHotposts, normalizeHotpost, readJsonArray } from "./hotpost-utils.mjs";
import { parseHotpostText } from "./hotpost-text-parser.mjs";

const root = path.resolve(process.cwd());
const inboxDir = path.join(root, "inputs", "hotpost-inbox");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const statusPath = path.join(root, "outputs", "collection-inbox-status.json");
const reportPath = path.join(root, "outputs", "collection-inbox-status.md");

fs.mkdirSync(inboxDir, { recursive: true });

const supported = new Set([".txt", ".md", ".json"]);
const files = fs
  .readdirSync(inboxDir)
  .filter((name) => !name.startsWith("."))
  .filter((name) => supported.has(path.extname(name).toLowerCase()));

const parseJsonFile = (filePath, defaults) => {
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  const items = Array.isArray(value) ? value : value.items || value.data || [];
  return Array.isArray(items)
    ? items.map((item) => normalizeHotpost(item, defaults))
    : [];
};

const parsedByFile = [];

for (const file of files) {
  const filePath = path.join(inboxDir, file);
  const ext = path.extname(file).toLowerCase();
  const defaults = {
    notes: `由 hotpost-inbox 自动收集：${file}`
  };

  try {
    const items = ext === ".json"
      ? parseJsonFile(filePath, defaults)
      : parseHotpostText(fs.readFileSync(filePath, "utf8"), defaults);
    parsedByFile.push({ file, ok: true, parsedCount: items.length, items });
  } catch (error) {
    parsedByFile.push({ file, ok: false, parsedCount: 0, error: error.message, items: [] });
  }
}

const incoming = parsedByFile.flatMap((item) => item.items);
const mergeResult = incoming.length
  ? mergeHotposts(hotpostsPath, incoming)
  : { total: readJsonArray(hotpostsPath).length, added: 0 };

const status = {
  generatedAt: new Date().toISOString(),
  inboxDir,
  fileCount: files.length,
  parsedCount: incoming.length,
  addedCount: mergeResult.added,
  hotpostsTotal: mergeResult.total,
  files: parsedByFile.map(({ items, ...item }) => item)
};

const report = [
  "# 小红书爆帖自动收集 Inbox",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `扫描目录：${inboxDir}`,
  `文件数量：${files.length}`,
  `解析数量：${incoming.length}`,
  `新增入库：${mergeResult.added}`,
  `热帖库总数：${mergeResult.total}`,
  "",
  "## 文件结果",
  "",
  ...(parsedByFile.length
    ? parsedByFile.map((item) => `- ${item.ok ? "OK" : "FAIL"} ${item.file}: ${item.parsedCount}${item.error ? ` (${item.error})` : ""}`)
    : ["- 暂无待收集文件"]),
  "",
  "## 使用方式",
  "",
  "把小红书热帖文本、复制结果、Markdown 或 JSON 放进：",
  "",
  "```text",
  "inputs/hotpost-inbox/",
  "```",
  "",
  "然后运行：",
  "",
  "```bash",
  "npm run collect:inbox",
  "```",
  "",
  "总控 `npm run control` 会自动执行这一步。"
].join("\n");

fs.mkdirSync(path.dirname(statusPath), { recursive: true });
fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
fs.writeFileSync(reportPath, report);

console.log(`已生成 ${statusPath}`);
console.log(`已生成 ${reportPath}`);
console.log(`Inbox 自动收集新增 ${mergeResult.added} 条，热帖库共 ${mergeResult.total} 条。`);
