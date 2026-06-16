import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "./load-env.mjs";
import { mergeHotposts, normalizeHotpost, readJsonArray, toNumber } from "./hotpost-utils.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const configPath = path.join(root, "inputs", "collect-keywords.json");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const statusPath = path.join(root, "outputs", "collection-apify-status.json");
const reportPath = path.join(root, "outputs", "collection-apify-status.md");

const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const keywords = Array.isArray(config.keywords) ? config.keywords : [];
const limit = Number(config.dailyLimitPerKeyword || 5);

const enabled = process.env.XHS_APIFY_ENABLED === "true";
const actorId = process.env.APIFY_XHS_ACTOR_ID || "kuaima/xiaohongshu-search";
const actorPath = actorId.replace("/", "~");
const token = process.env.APIFY_TOKEN || "";
const cookie = process.env.XHS_COOKIE || process.env.APIFY_XHS_COOKIE || "";
const endpoint = `https://api.apify.com/v2/acts/${actorPath}/run-sync-get-dataset-items`;

const writeStatus = (status, report) => {
  fs.mkdirSync(path.dirname(statusPath), { recursive: true });
  fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
  fs.writeFileSync(reportPath, report);
  console.log(`已生成 ${statusPath}`);
  console.log(`已生成 ${reportPath}`);
};

const pick = (object, keys) => {
  for (const key of keys) {
    if (object?.[key] !== undefined && object?.[key] !== null && object?.[key] !== "") {
      return object[key];
    }
  }
  return "";
};

const buildUrl = (item) => {
  const direct = pick(item, ["url", "noteUrl", "note_url", "link", "share_url", "shareUrl"]);
  if (direct) return String(direct);

  const noteId = pick(item, ["noteId", "note_id", "id", "aweme_id"]);
  return noteId ? `https://www.xiaohongshu.com/explore/${noteId}` : "";
};

const normalizeApifyItem = (item, keywordConfig) => {
  const rawUser = item.user || item.user_info || item.author || {};
  const interact = item.interact_info || item.interactInfo || item.stats || item;
  const title = pick(item, [
    "title",
    "display_title",
    "displayTitle",
    "noteTitle",
    "desc",
    "description"
  ]);
  const body = pick(item, ["desc", "description", "content", "text"]);
  const author = pick(rawUser, ["nickname", "name", "user_name"]) || pick(item, ["nickname", "author"]);

  return normalizeHotpost(
    {
      title: title || String(body).slice(0, 36),
      url: buildUrl(item),
      authorType: author || "小红书作者",
      likes: toNumber(pick(interact, ["likes", "likeCount", "liked_count", "likedCount"])),
      comments: toNumber(pick(interact, ["comments", "commentCount", "comment_count"])),
      favorites: toNumber(
        pick(interact, ["favorites", "collectCount", "collected_count", "collectedCount"])
      ),
      longTailKeyword: keywordConfig.keyword,
      topic: keywordConfig.keyword,
      accountRole: keywordConfig.accountRoleHint,
      searchFunnel: keywordConfig.searchFunnelHint,
      hook: title || keywordConfig.keyword,
      notes: `由 Apify 小红书搜索采集导入。关键词：${keywordConfig.keyword}`
    },
    {
      keyword: keywordConfig.keyword,
      accountRoleHint: keywordConfig.accountRoleHint,
      searchFunnelHint: keywordConfig.searchFunnelHint
    }
  );
};

const buildInput = (keywordConfig) => ({
  search_key: keywordConfig.keyword,
  maxItems: limit,
  filter: keywordConfig.apifyFilter || config.apifyFilter || "general",
  categories: keywordConfig.apifyCategories || config.apifyCategories || "notes",
  cookie_val: cookie
});

if (!enabled) {
  const status = {
    generatedAt: new Date().toISOString(),
    mode: "apify",
    actorId,
    skipped: true,
    reason: "XHS_APIFY_ENABLED 未设置为 true"
  };
  const report = [
    "# Apify 小红书搜索采集状态",
    "",
    `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
    "",
    "状态：已关闭",
    "",
    "当前 `XHS_APIFY_ENABLED` 不是 `true`，所以不会调用 Apify。",
    "",
    "可用替代方案：",
    "",
    "- `inputs/external-hotposts.json`：导入合规来源的 JSON 热帖数据。",
    "- `inputs/hotposts-import.txt`：粘贴文本热帖数据。",
    "- `XHS_SOURCE_URL`：接入你自己的 JSON 数据源。"
  ].join("\n");

  writeStatus(status, report);
  console.log("Apify 采集已关闭：XHS_APIFY_ENABLED 未设置为 true");
  process.exit(0);
}

const runKeyword = async (keywordConfig) => {
  const actorInput = buildInput(keywordConfig);
  const url = new URL(endpoint);
  url.searchParams.set("token", token);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json"
      },
      body: JSON.stringify(actorInput)
    });

    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = [];
    }

    const items = Array.isArray(payload) ? payload : payload?.items || payload?.data || [];
    const normalized = Array.isArray(items)
      ? items.slice(0, limit).map((item) => normalizeApifyItem(item, keywordConfig))
      : [];

    return {
      keyword: keywordConfig.keyword,
      ok: response.ok && normalized.length > 0,
      httpStatus: response.status,
      itemCount: normalized.length,
      message: response.ok ? "OK" : text.slice(0, 240),
      items: normalized
    };
  } catch (error) {
    return {
      keyword: keywordConfig.keyword,
      ok: false,
      httpStatus: null,
      itemCount: 0,
      message: error.message,
      items: []
    };
  }
};

if (!token || !cookie) {
  const missing = [
    !token ? "APIFY_TOKEN" : "",
    !cookie ? "XHS_COOKIE 或 APIFY_XHS_COOKIE" : ""
  ].filter(Boolean);
  const status = {
    generatedAt: new Date().toISOString(),
    mode: "apify",
    actorId,
    skipped: true,
    missing
  };
  const report = [
    "# Apify 小红书搜索采集状态",
    "",
    `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
    "",
    "状态：已跳过",
    "",
    "## 缺少配置",
    "",
    ...missing.map((item) => `- ${item}`),
    "",
    "## 配置方式",
    "",
    "在 `.env.local` 中填入：",
    "",
    "```text",
    "APIFY_TOKEN=你的 Apify token",
    "XHS_COOKIE=你在浏览器登录小红书后的 cookie_val",
    "```",
    "",
    "本脚本只调用你配置的第三方数据源，不做验证码绕过、签名逆向或账号互动。"
  ].join("\n");

  writeStatus(status, report);
  console.log(`Apify 采集已跳过：缺少 ${missing.join("、")}`);
  process.exit(0);
}

const results = [];
for (const keyword of keywords) {
  results.push(await runKeyword(keyword));
}

const collected = results.flatMap((result) => result.items);
const mergeResult = collected.length
  ? mergeHotposts(hotpostsPath, collected)
  : { total: readJsonArray(hotpostsPath).length, added: 0 };

const status = {
  generatedAt: new Date().toISOString(),
  mode: "apify",
  actorId,
  attemptedKeywords: keywords.length,
  collectedCount: collected.length,
  addedCount: mergeResult.added,
  hotpostsTotal: mergeResult.total,
  safety: "不发布、不点赞、不评论、不关注；仅调用用户配置的 Apify 数据源采集公开搜索结果。",
  results: results.map(({ items, ...result }) => result)
};

const report = [
  "# Apify 小红书搜索采集状态",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `Actor：${actorId}`,
  `关键词数：${keywords.length}`,
  `采集数量：${collected.length}`,
  `新增合并：${mergeResult.added}`,
  `热帖库总数：${mergeResult.total}`,
  "",
  "## 关键词结果",
  "",
  ...results.flatMap((result) => [
    `### ${result.keyword}`,
    "",
    `- 状态：${result.ok ? "成功" : "未采集到数据"}`,
    `- HTTP：${result.httpStatus ?? "无"}`,
    `- 数量：${result.itemCount}`,
    `- 提示：${result.message || "无"}`,
    ""
  ]),
  "## 合规边界",
  "",
  "- 只采集搜索结果并写入本地热帖库。",
  "- 不自动发布、点赞、评论、收藏、关注。",
  "- 不处理验证码、登录弹窗、签名逆向或风控绕过。"
].join("\n");

writeStatus(status, report);
console.log(`Apify 采集完成，新增 ${mergeResult.added} 条。`);
