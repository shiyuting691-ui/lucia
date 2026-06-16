import fs from "node:fs";
import path from "node:path";
import { mergeHotposts, normalizeHotpost, readJsonArray } from "./hotpost-utils.mjs";
import { loadEnvFile } from "./load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const localSourcePath = path.join(root, "inputs", "external-hotposts.json");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const statusPath = path.join(root, "outputs", "collection-source-status.json");
const reportPath = path.join(root, "outputs", "collection-source-status.md");

const sourceUrl = process.env.XHS_SOURCE_URL;

const readRemoteSource = async () => {
  if (!sourceUrl) return { items: [], source: "none", message: "未配置 XHS_SOURCE_URL" };

  const response = await fetch(sourceUrl, {
    headers: {
      accept: "application/json"
    }
  });
  const payload = await response.json();
  const items = Array.isArray(payload) ? payload : payload.items || payload.data || [];
  return {
    items: Array.isArray(items) ? items : [],
    source: sourceUrl,
    message: `HTTP ${response.status}`
  };
};

let remote = { items: [], source: "none", message: "未配置 XHS_SOURCE_URL" };
try {
  remote = await readRemoteSource();
} catch (error) {
  remote = { items: [], source: sourceUrl || "none", message: error.message };
}

const localItems = readJsonArray(localSourcePath);
const normalized = [...localItems, ...remote.items].map((item) =>
  normalizeHotpost(item, {
    notes: "由外部合规数据源导入。"
  })
);
const mergeResult = normalized.length
  ? mergeHotposts(hotpostsPath, normalized)
  : { total: readJsonArray(hotpostsPath).length, added: 0 };

const status = {
  generatedAt: new Date().toISOString(),
  localSource: localSourcePath,
  remoteSource: remote.source,
  remoteMessage: remote.message,
  importedCount: normalized.length,
  addedCount: mergeResult.added,
  hotpostsTotal: mergeResult.total
};

const report = [
  "# 外部热帖数据源采集状态",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `本地导入：${localItems.length}条`,
  `远程数据源：${remote.source}`,
  `远程状态：${remote.message}`,
  `本次标准化：${normalized.length}条`,
  `新增合并：${mergeResult.added}条`,
  `热帖库总数：${mergeResult.total}条`,
  "",
  "## 使用方式",
  "",
  "- 把合规来源导出的 JSON 放到 `inputs/external-hotposts.json`。",
  "- 或设置 `XHS_SOURCE_URL`，让每日任务读取你自己的数据接口。",
  "- 数据会去重合并到 `inputs/hotposts.json`，再进入分析和发文流程。"
].join("\n");

fs.mkdirSync(path.dirname(statusPath), { recursive: true });
fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
fs.writeFileSync(reportPath, report);

console.log(`已生成 ${statusPath}`);
console.log(`已生成 ${reportPath}`);
console.log(`外部数据源新增 ${mergeResult.added} 条，热帖库共 ${mergeResult.total} 条。`);
