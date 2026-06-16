import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "./load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const outputsDir = path.join(root, "outputs");
const statusJsonPath = path.join(outputsDir, "cloud-check-status.json");
const statusMdPath = path.join(outputsDir, "cloud-check-status.md");

const modeArg = process.argv.slice(2).find((arg) => arg.startsWith("--mode="));
const mode = modeArg ? modeArg.split("=")[1] : process.env.XHS_WORKFLOW_MODE || "daily";

const isEnabled = (key) => process.env[key] === "true";
const hasValue = (key) => Boolean(process.env[key]?.trim());

const checks = [
  {
    key: "NODE_ENV",
    level: "warn",
    purpose: "建议在云端设置为 production，便于区分本地与云端运行"
  },
  {
    key: "XHS_RUN_ID",
    level: "warn",
    purpose: "可选；为空时 controller 会自动生成 runId"
  },
  {
    key: "XHS_AUTO_PUSH_WXPUSHER",
    level: "warn",
    purpose: "可选；daily 默认可不启用 WxPusher 推送"
  },
  {
    key: "WXPUSHER_TOKEN",
    level: isEnabled("XHS_AUTO_PUSH_WXPUSHER") && mode === "full" ? "fail" : "warn",
    purpose: "WxPusher appToken；仅启用 WxPusher 推送时需要"
  },
  {
    key: "WXPUSHER_UID",
    level: isEnabled("XHS_AUTO_PUSH_WXPUSHER") && mode === "full" ? "fail" : "warn",
    purpose: "WxPusher 接收用户 UID；仅启用 WxPusher 推送时需要"
  },
  {
    key: "XHS_AUTO_PUSH_LARK",
    level: "warn",
    purpose: "可选；daily 默认可不启用飞书推送"
  },
  {
    key: "LARK_APP_ID",
    level: isEnabled("XHS_AUTO_PUSH_LARK") && mode === "full" ? "fail" : "warn",
    purpose: "飞书自建应用 App ID；仅启用飞书推送/采集时需要"
  },
  {
    key: "LARK_APP_SECRET",
    level: isEnabled("XHS_AUTO_PUSH_LARK") && mode === "full" ? "fail" : "warn",
    purpose: "飞书自建应用 App Secret；仅启用飞书推送/采集时需要"
  },
  {
    key: "LARK_RECEIVE_ID_TYPE",
    level: "warn",
    purpose: "飞书消息接收 ID 类型；默认可由脚本使用 chat_id"
  },
  {
    key: "LARK_RECEIVE_ID",
    level: isEnabled("XHS_AUTO_PUSH_LARK") && mode === "full" ? "fail" : "warn",
    purpose: "飞书接收人或群聊 ID；仅启用飞书推送时需要"
  },
  {
    key: "LARK_SHEET_URLS",
    aliases: ["LARK_FILE_SOURCES_JSON"],
    level: "warn",
    purpose: "飞书表格采集数据源；daily/demo 可以缺失"
  },
  {
    key: "WECHAT_PUSH_ENABLED",
    level: "warn",
    purpose: "可选；企业微信 webhook 推送开关"
  },
  {
    key: "WECHAT_WEBHOOK_URL",
    level: isEnabled("WECHAT_PUSH_ENABLED") && mode === "full" ? "fail" : "warn",
    purpose: "企业微信群机器人 webhook；仅启用企业微信推送时需要"
  },
  {
    key: "XHS_APIFY_ENABLED",
    level: "warn",
    purpose: "可选；Apify 小红书采集开关"
  },
  {
    key: "APIFY_TOKEN",
    level: isEnabled("XHS_APIFY_ENABLED") && mode === "full" ? "fail" : "warn",
    purpose: "Apify token；仅启用 Apify 采集时需要"
  },
  {
    key: "APIFY_XHS_ACTOR_ID",
    level: "warn",
    purpose: "Apify Actor ID；为空时可由脚本使用默认 actor"
  },
  {
    key: "XHS_COOKIE",
    aliases: ["APIFY_XHS_COOKIE"],
    level: isEnabled("XHS_APIFY_ENABLED") && mode === "full" ? "fail" : "warn",
    purpose: "Apify 使用的小红书登录态；仅启用 Apify 采集时需要"
  }
];

const checkConfigured = (item) => [item.key, ...(item.aliases || [])].some(hasValue);

const rows = checks.map((item) => {
  const configured = checkConfigured(item);
  const status = configured ? "OK" : item.level === "fail" ? "FAIL" : "WARN";
  return {
    key: item.aliases?.length ? `${item.key} / ${item.aliases.join(" / ")}` : item.key,
    status,
    configured,
    required: item.level === "fail",
    purpose: item.purpose
  };
});

const failed = rows.filter((row) => row.status === "FAIL");
const warned = rows.filter((row) => row.status === "WARN");
const ok = failed.length === 0;

const markdown = [
  "# 云端环境检查",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `检查模式：${mode}`,
  `整体状态：${ok ? "通过" : "需处理"}`,
  "",
  "## 检查项",
  "",
  ...rows.flatMap((row) => [
    `- ${row.status} ${row.key}`,
    `  - 用途：${row.purpose}`,
    `  - 必填：${row.required ? "是" : "否"}`
  ]),
  "",
  "## 汇总",
  "",
  `- FAIL：${failed.length ? failed.map((row) => row.key).join("、") : "无"}`,
  `- WARN：${warned.length ? warned.map((row) => row.key).join("、") : "无"}`
].join("\n");

const status = {
  generatedAt: new Date().toISOString(),
  mode,
  ok,
  failed: failed.map((row) => row.key),
  warnings: warned.map((row) => row.key),
  checks: rows
};

fs.mkdirSync(outputsDir, { recursive: true });
fs.writeFileSync(statusJsonPath, JSON.stringify(status, null, 2));
fs.writeFileSync(statusMdPath, markdown);

console.log(markdown);
console.log("");
console.log(`已生成 ${statusJsonPath}`);
console.log(`已生成 ${statusMdPath}`);

if (!ok) {
  process.exitCode = 1;
}
