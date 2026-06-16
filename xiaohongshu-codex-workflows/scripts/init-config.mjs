import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const envPath = path.join(root, ".env.local");

const defaults = [
  ["WECHAT_WEBHOOK_URL", ""],
  ["WECHAT_PUSH_ENABLED", "false"],
  ["WXPUSHER_TOKEN", ""],
  ["WXPUSHER_UID", ""],
  ["XHS_AUTO_PUSH_WXPUSHER", "false"],
  ["LARK_APP_ID", ""],
  ["LARK_APP_SECRET", ""],
  ["LARK_RECEIVE_ID_TYPE", "chat_id"],
  ["LARK_RECEIVE_ID", ""],
  ["XHS_AUTO_PUSH_LARK", "false"],
  ["LARK_SHEET_URLS", ""],
  ["LARK_SHEET_RANGE", "A1:Z300"],
  ["LARK_FILE_SOURCES_JSON", ""],
  ["LARK_LOCAL_EXPORT_DIR", "inputs/lark-course-sheets"],
  ["XHS_SOURCE_URL", ""],
  ["APIFY_TOKEN", ""],
  ["XHS_COOKIE", ""],
  ["APIFY_XHS_COOKIE", ""],
  ["APIFY_XHS_ACTOR_ID", "kuaima/xiaohongshu-search"],
  ["XHS_APIFY_ENABLED", "false"]
];

const existing = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8") : "";
const existingKeys = new Set();

for (const line of existing.split("\n")) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
  existingKeys.add(trimmed.split("=")[0].trim());
}

const additions = defaults
  .filter(([key]) => !existingKeys.has(key))
  .map(([key, value]) => `${key}=${value}`);

if (additions.length) {
  const prefix = existing && !existing.endsWith("\n") ? "\n" : "";
  fs.writeFileSync(envPath, `${existing}${prefix}${additions.join("\n")}\n`);
}

console.log(additions.length ? `已补齐配置键：${additions.map((line) => line.split("=")[0]).join("、")}` : "配置键已齐全。");
console.log("不会覆盖已有密钥。");
