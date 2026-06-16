import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "./load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const digestPath = path.join(root, "outputs", "wechat-daily-digest.txt");
const statusPath = path.join(root, "outputs", "wechat-push-status.json");
const pushEnabled = process.env.WECHAT_PUSH_ENABLED === "true";
const webhookUrl = process.env.WECHAT_WEBHOOK_URL;

const writeStatus = (status) => {
  fs.mkdirSync(path.dirname(statusPath), { recursive: true });
  fs.writeFileSync(
    statusPath,
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        ...status
      },
      null,
      2
    )
  );
};

if (!pushEnabled) {
  const message = "企业微信自动推送已关闭：WECHAT_PUSH_ENABLED 未设置为 true。";
  writeStatus({ ok: false, skipped: true, reason: message });
  console.log(message);
  process.exit(0);
}

if (!webhookUrl) {
  const message = "未配置 WECHAT_WEBHOOK_URL，已跳过微信自动推送。";
  writeStatus({ ok: false, skipped: true, reason: message });
  console.log(message);
  process.exit(0);
}

if (!fs.existsSync(digestPath)) {
  throw new Error(`未找到微信日报摘要：${digestPath}`);
}

const content = fs.readFileSync(digestPath, "utf8").trim();

if (!content) {
  const message = "微信日报摘要为空，已跳过推送。";
  writeStatus({ ok: false, skipped: true, reason: message });
  console.log(message);
  process.exit(0);
}

const response = await fetch(webhookUrl, {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    msgtype: "text",
    text: {
      content
    }
  })
});

const body = await response.text();

if (!response.ok) {
  writeStatus({
    ok: false,
    skipped: false,
    status: response.status,
    response: body
  });
  throw new Error(`微信推送失败：HTTP ${response.status} ${body}`);
}

writeStatus({
  ok: true,
  skipped: false,
  status: response.status,
  response: body
});

console.log("微信自动推送已完成。");
