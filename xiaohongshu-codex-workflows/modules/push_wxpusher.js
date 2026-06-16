import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "../scripts/load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const outputDir = path.join(root, "outputs");
const statusPath = path.join(outputDir, "wxpusher-push-status.json");
const endpoint = "https://wxpusher.zjiecode.com/api/send/message";

const writeStatus = (status) => {
  fs.mkdirSync(outputDir, { recursive: true });
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

const escapeHtml = (value) =>
  value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

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

const formatDigestAsHtml = (text) => {
  const lines = text.trim().split("\n");
  const title = escapeHtml(lines[0] || "小红书今日待确认");
  const body = escapeHtml(lines.slice(1).join("\n").trim()).replace(/\n/g, "<br>");

  return [
    `<h2>${title}</h2>`,
    body ? `<p>${body}</p>` : "",
    "<hr>",
    "<p>由本地小红书运营工作流自动生成。</p>"
  ]
    .filter(Boolean)
    .join("\n");
};

const appToken = process.env.WXPUSHER_TOKEN?.trim();
const uid = process.env.WXPUSHER_UID?.trim();

if (!appToken || !uid) {
  const missing = [
    !appToken ? "WXPUSHER_TOKEN" : "",
    !uid ? "WXPUSHER_UID" : ""
  ].filter(Boolean);
  const message = `WxPusher 推送已跳过：缺少 ${missing.join("、")}`;
  writeStatus({ ok: false, skipped: true, missing, reason: message });
  console.log(message);
  process.exit(0);
}

const digest = findLatestDigest();

if (!digest) {
  const message = "WxPusher 推送已跳过：未找到 outputs/wechat-daily-*.txt";
  writeStatus({ ok: false, skipped: true, reason: message });
  console.log(message);
  process.exit(0);
}

const text = fs.readFileSync(digest.path, "utf8").trim();

if (!text) {
  const message = `WxPusher 推送已跳过：${digest.name} 内容为空`;
  writeStatus({ ok: false, skipped: true, digest: digest.name, reason: message });
  console.log(message);
  process.exit(0);
}

const payload = {
  appToken,
  content: formatDigestAsHtml(text),
  contentType: 2,
  uids: [uid]
};

const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 15000);

try {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal: controller.signal
  });

  const responseText = await response.text();
  let responseBody = responseText;
  try {
    responseBody = JSON.parse(responseText);
  } catch {
    // Keep raw response text for non-JSON failures.
  }

  const ok = response.ok && (responseBody?.code === 1000 || responseBody?.success === true);

  writeStatus({
    ok,
    skipped: false,
    digest: digest.name,
    status: response.status,
    response: responseBody
  });

  if (!ok) {
    throw new Error(`WxPusher 推送失败：HTTP ${response.status} ${responseText}`);
  }

  console.log(`WxPusher 推送已完成：${digest.name}`);
} catch (error) {
  const message = error.name === "AbortError"
    ? "WxPusher 推送失败：请求超时"
    : `WxPusher 推送失败：${error.message}`;
  writeStatus({
    ok: false,
    skipped: false,
    digest: digest.name,
    reason: message
  });
  throw new Error(message);
} finally {
  clearTimeout(timeout);
}
