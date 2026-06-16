import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "../scripts/load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const outputDir = path.join(root, "outputs");
const statusPath = path.join(outputDir, "lark-push-status.json");

const appId = process.env.LARK_APP_ID?.trim();
const appSecret = process.env.LARK_APP_SECRET?.trim();
const receiveId = process.env.LARK_RECEIVE_ID?.trim();
const receiveIdType = process.env.LARK_RECEIVE_ID_TYPE?.trim() || "chat_id";

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

const findLatestDigest = () => {
  if (!fs.existsSync(outputDir)) return null;

  const files = fs
    .readdirSync(outputDir)
    .filter((name) => /^wechat-daily-.*\.txt$/.test(name))
    .map((name) => {
      const filePath = path.join(outputDir, name);
      return {
        name,
        path: filePath,
        mtimeMs: fs.statSync(filePath).mtimeMs
      };
    })
    .sort((a, b) => b.mtimeMs - a.mtimeMs);

  return files[0] || null;
};

const missing = [
  !appId ? "LARK_APP_ID" : "",
  !appSecret ? "LARK_APP_SECRET" : "",
  !receiveId ? "LARK_RECEIVE_ID" : ""
].filter(Boolean);

if (missing.length) {
  const message = `飞书推送缺少配置：${missing.join("、")}`;
  writeStatus({ ok: false, skipped: true, reason: message });
  console.log(message);
  process.exit(0);
}

const digestFile = findLatestDigest();

if (!digestFile) {
  const message = "飞书推送已跳过：未找到 outputs/wechat-daily-*.txt";
  writeStatus({ ok: false, skipped: true, reason: message });
  console.log(message);
  process.exit(0);
}

const digest = fs.readFileSync(digestFile.path, "utf8").trim();

if (!digest) {
  const message = `飞书推送已跳过：${digestFile.name} 内容为空`;
  writeStatus({ ok: false, skipped: true, digest: digestFile.name, reason: message });
  console.log(message);
  process.exit(0);
}

const getTenantAccessToken = async () => {
  const response = await fetch("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8"
    },
    body: JSON.stringify({
      app_id: appId,
      app_secret: appSecret
    })
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.code !== 0) {
    throw new Error(`获取飞书 tenant_access_token 失败：HTTP ${response.status} ${JSON.stringify(body)}`);
  }

  return body.tenant_access_token;
};

const sendMessage = async (tenantAccessToken) => {
  const content = [
    "小红书每日待确认",
    "",
    digest,
    "",
    "注意：这条消息只用于确认，不自动发布。"
  ].join("\n");

  const response = await fetch(
    `https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=${encodeURIComponent(receiveIdType)}`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${tenantAccessToken}`,
        "Content-Type": "application/json; charset=utf-8"
      },
      body: JSON.stringify({
        receive_id: receiveId,
        msg_type: "text",
        content: JSON.stringify({ text: content.slice(0, 14000) })
      })
    }
  );

  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.code !== 0) {
    throw new Error(`飞书消息发送失败：HTTP ${response.status} ${JSON.stringify(body)}`);
  }

  return body;
};

try {
  const tenantAccessToken = await getTenantAccessToken();
  const response = await sendMessage(tenantAccessToken);
  writeStatus({
    ok: true,
    skipped: false,
    digest: digestFile.name,
    receiveIdType,
    response
  });
  console.log(`飞书推送已完成：${digestFile.name}`);
} catch (error) {
  writeStatus({
    ok: false,
    skipped: false,
    digest: digestFile.name,
    receiveIdType,
    error: error.message
  });
  throw error;
}
