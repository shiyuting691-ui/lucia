import path from "node:path";
import { loadEnvFile } from "./load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const checks = [
  {
    key: "WECHAT_PUSH_ENABLED",
    purpose: "是否启用企业微信群机器人自动推送",
    requiredFor: "npm run push:wechat",
    optional: true,
    defaultValue: "false"
  },
  {
    key: "WECHAT_WEBHOOK_URL",
    purpose: "企业微信群机器人推送微信日报",
    requiredFor: "npm run push:wechat",
    optional: process.env.WECHAT_PUSH_ENABLED !== "true"
  },
  {
    key: "XHS_AUTO_PUSH_WXPUSHER",
    purpose: "总控工作流是否自动执行 WxPusher 推送",
    requiredFor: "npm run all / npm run control",
    optional: true,
    defaultValue: "false"
  },
  {
    key: "WXPUSHER_TOKEN",
    purpose: "WxPusher 微信推送 appToken",
    requiredFor: "npm run push:wxpusher",
    optional: process.env.XHS_AUTO_PUSH_WXPUSHER !== "true"
  },
  {
    key: "WXPUSHER_UID",
    purpose: "WxPusher 接收用户 UID",
    requiredFor: "npm run push:wxpusher",
    optional: process.env.XHS_AUTO_PUSH_WXPUSHER !== "true"
  },
  {
    key: "XHS_AUTO_PUSH_LARK",
    purpose: "总控工作流是否自动执行飞书推送",
    requiredFor: "npm run all / npm run control",
    optional: true,
    defaultValue: "false"
  },
  {
    key: "LARK_APP_ID",
    purpose: "飞书自建应用 App ID",
    requiredFor: "npm run push:lark",
    optional: process.env.XHS_AUTO_PUSH_LARK !== "true"
  },
  {
    key: "LARK_APP_SECRET",
    purpose: "飞书自建应用 App Secret",
    requiredFor: "npm run push:lark",
    optional: process.env.XHS_AUTO_PUSH_LARK !== "true"
  },
  {
    key: "LARK_RECEIVE_ID_TYPE",
    purpose: "飞书消息接收 ID 类型，例如 chat_id/open_id/user_id",
    requiredFor: "npm run push:lark",
    optional: true,
    defaultValue: "chat_id"
  },
  {
    key: "LARK_RECEIVE_ID",
    purpose: "飞书接收人或群聊 ID",
    requiredFor: "npm run push:lark",
    optional: process.env.XHS_AUTO_PUSH_LARK !== "true"
  },
  {
    key: "LARK_SHEET_URLS",
    aliases: ["LARK_FILE_SOURCES_JSON"],
    purpose: "从飞书电子表格读取热帖/选题/素材数据",
    requiredFor: "npm run collect:lark",
    optional: true
  },
  {
    key: "LARK_SHEET_RANGE",
    purpose: "飞书电子表格读取范围",
    requiredFor: "npm run collect:lark",
    optional: true,
    defaultValue: "A1:Z300"
  },
  {
    key: "LARK_LOCAL_EXPORT_DIR",
    purpose: "飞书表格导出文件兜底目录（.xlsx/.csv）",
    requiredFor: "npm run collect:lark",
    optional: true,
    defaultValue: "inputs/lark-course-sheets"
  },
  {
    key: "XHS_SOURCE_URL",
    purpose: "读取你自己的合规热帖 JSON 数据源",
    requiredFor: "npm run collect:source",
    optional: true
  },
  {
    key: "SOCIAL_ASSISTANT_DIR",
    purpose: "社媒助手表格目录",
    requiredFor: "npm run collect:social",
    optional: true,
    defaultValue: "/Users/meilucia/Downloads/社媒助手"
  },
  {
    key: "SOCIAL_ASSISTANT_MIN_TOTAL",
    purpose: "社媒助手爆款筛选的最低总互动门槛",
    requiredFor: "npm run collect:social",
    optional: true,
    defaultValue: "50"
  },
  {
    key: "SOCIAL_ASSISTANT_MAX_PER_FILE",
    purpose: "每个社媒助手表格最多导入多少条爆款",
    requiredFor: "npm run collect:social",
    optional: true,
    defaultValue: "30"
  },
  {
    key: "SOCIAL_ASSISTANT_MAX_PER_ROLE",
    purpose: "每个账号 SOP 最多保留多少条参考爆帖",
    requiredFor: "npm run collect:social / npm run draft:roles",
    optional: true,
    defaultValue: "10"
  },
  {
    key: "XHS_APIFY_ENABLED",
    purpose: "是否启用 Apify 小红书采集",
    requiredFor: "npm run collect:apify",
    optional: true,
    defaultValue: "false"
  },
  {
    key: "APIFY_TOKEN",
    purpose: "调用 Apify 小红书搜索采集器",
    requiredFor: "npm run collect:apify",
    optional: process.env.XHS_APIFY_ENABLED !== "true"
  },
  {
    key: "XHS_COOKIE",
    aliases: ["APIFY_XHS_COOKIE"],
    purpose: "交给 Apify 采集器使用的小红书登录态参数",
    requiredFor: "npm run collect:apify",
    optional: process.env.XHS_APIFY_ENABLED !== "true"
  },
  {
    key: "APIFY_XHS_ACTOR_ID",
    purpose: "Apify Actor ID",
    requiredFor: "npm run collect:apify",
    optional: true,
    defaultValue: "kuaima/xiaohongshu-search"
  }
];

const isSet = (key) => Boolean(process.env[key]?.trim());

const rows = checks.map((item) => {
  const aliases = item.aliases || [];
  const keys = [item.key, ...aliases];
  const configured = keys.some(isSet) || Boolean(item.defaultValue);
  return {
    key: aliases.length ? `${item.key} / ${aliases.join(" / ")}` : item.key,
    status: configured ? "已配置" : item.optional ? "未配置（可选）" : "缺失",
    purpose: item.purpose,
    requiredFor: item.requiredFor
  };
});

const missing = rows.filter((row) => row.status === "缺失");

console.log("小红书工作流配置检查");
console.log("");
for (const row of rows) {
  console.log(`- ${row.key}: ${row.status}`);
  console.log(`  用途: ${row.purpose}`);
  console.log(`  影响: ${row.requiredFor}`);
}

console.log("");
if (missing.length) {
  console.log(`还缺 ${missing.length} 项必需配置：${missing.map((row) => row.key).join("、")}`);
  process.exitCode = 1;
} else {
  console.log("必需配置已齐全。");
}
