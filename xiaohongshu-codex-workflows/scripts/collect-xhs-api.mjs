import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const configPath = path.join(root, "inputs", "collect-keywords.json");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const statusPath = path.join(root, "outputs", "collection-api-status.json");
const reportPath = path.join(root, "outputs", "collection-api-status.md");

const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const keywords = Array.isArray(config.keywords) ? config.keywords : [];
const limit = Number(config.dailyLimitPerKeyword || 5);

const endpoint = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes";

const toNumber = (value) => {
  if (typeof value === "number") return value;
  if (!value) return 0;
  const normalized = String(value).trim();
  if (normalized.endsWith("万")) return Math.round(Number(normalized.slice(0, -1)) * 10000);
  const parsed = Number(normalized.replace(/[^\d.]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
};

const extractItems = (payload) => {
  if (Array.isArray(payload?.data?.items)) return payload.data.items;
  if (Array.isArray(payload?.data?.notes)) return payload.data.notes;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
};

const normalizeItem = (raw, keywordConfig) => {
  const card = raw.note_card || raw.noteCard || raw.card || raw;
  const interact = card.interact_info || card.interactInfo || {};
  const user = card.user || card.user_info || card.userInfo || {};
  const noteId = raw.id || raw.note_id || card.note_id || card.noteId || card.id || "";
  const xsecToken = raw.xsec_token || card.xsec_token || "";
  const url = noteId
    ? `https://www.xiaohongshu.com/explore/${noteId}${xsecToken ? `?xsec_token=${encodeURIComponent(xsecToken)}` : ""}`
    : "";

  return {
    title: card.display_title || card.title || card.desc?.slice(0, 36) || keywordConfig.keyword,
    url,
    accountRole: keywordConfig.accountRoleHint || "ip",
    searchFunnel: keywordConfig.searchFunnelHint || "midstream",
    authorType: user.nickname ? `${user.nickname}` : "小红书作者",
    likes: toNumber(interact.liked_count || interact.likedCount || interact.like_count),
    comments: toNumber(interact.comment_count || interact.commentCount),
    favorites: toNumber(interact.collected_count || interact.collectedCount || interact.collect_count),
    topic: keywordConfig.keyword,
    audience: "小红书搜索用户",
    longTailKeyword: keywordConfig.keyword,
    hook: card.display_title || card.title || "搜索结果标题",
    structure: ["搜索标题切入", "围绕具体痛点展开", "评论区承接问题"],
    tone: ["真实", "搜索友好"],
    commentTrigger: "你现在卡在哪一步",
    cta: "评论区说具体情况",
    notes: `由合规接口探测采集，关键词：${keywordConfig.keyword}`
  };
};

const probeKeyword = async (keywordConfig) => {
  const body = {
    keyword: keywordConfig.keyword,
    page: 1,
    page_size: limit,
    search_id: "",
    sort: "general",
    note_type: 0,
    ext_flags: [],
    filters: [],
    geo: ""
  };

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        accept: "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        origin: "https://www.xiaohongshu.com",
        referer: `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keywordConfig.keyword)}`,
        "user-agent": "Mozilla/5.0"
      },
      body: JSON.stringify(body)
    });

    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text.slice(0, 500) };
    }

    const items = extractItems(payload).slice(0, limit);
    return {
      keyword: keywordConfig.keyword,
      ok: response.ok && items.length > 0,
      httpStatus: response.status,
      platformCode: payload?.code ?? null,
      platformMessage: payload?.msg || payload?.message || "",
      itemCount: items.length,
      items: items.map((item) => normalizeItem(item, keywordConfig))
    };
  } catch (error) {
    return {
      keyword: keywordConfig.keyword,
      ok: false,
      httpStatus: null,
      platformCode: null,
      platformMessage: error.message,
      itemCount: 0,
      items: []
    };
  }
};

const results = [];

for (const keyword of keywords) {
  results.push(await probeKeyword(keyword));
}

const collected = results.flatMap((result) => result.items);
const status = {
  generatedAt: new Date().toISOString(),
  endpoint,
  attemptedKeywords: keywords.length,
  collectedCount: collected.length,
  mode: "public_api_probe",
  safety: "不读取 Chrome Cookie，不生成签名，不绕过验证码或风控；失败时只记录原因。",
  results: results.map(({ items, ...result }) => result)
};

if (collected.length > 0) {
  const existing = JSON.parse(fs.readFileSync(hotpostsPath, "utf8"));
  const seen = new Set(existing.map((item) => item.url || item.title));
  const merged = [...existing];

  for (const item of collected) {
    const key = item.url || item.title;
    if (!seen.has(key)) {
      merged.push(item);
      seen.add(key);
    }
  }

  fs.writeFileSync(hotpostsPath, JSON.stringify(merged, null, 2));
}

const report = [
  "# 小红书结构化采集状态",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `采集数量：${collected.length}`,
  "",
  "## 安全边界",
  "",
  "- 不读取 Chrome Cookie。",
  "- 不生成或逆向平台签名。",
  "- 不绕过登录、验证码或风控。",
  "- 只使用正常公开请求；失败原因会记录下来。",
  "",
  "## 关键词结果",
  "",
  ...results.flatMap((result) => [
    `### ${result.keyword}`,
    "",
    `- 状态：${result.ok ? "成功" : "未采集到结构化数据"}`,
    `- HTTP：${result.httpStatus ?? "无"}`,
    `- 平台代码：${result.platformCode ?? "无"}`,
    `- 平台提示：${result.platformMessage || "无"}`,
    `- 数量：${result.itemCount}`,
    ""
  ])
].join("\n");

fs.mkdirSync(path.dirname(statusPath), { recursive: true });
fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
fs.writeFileSync(reportPath, report);

console.log(`已生成 ${statusPath}`);
console.log(`已生成 ${reportPath}`);
if (collected.length > 0) {
  console.log(`已合并 ${collected.length} 条结构化采集结果到 ${hotpostsPath}`);
} else {
  console.log("未采集到结构化结果；通常是平台要求登录态或签名，已记录状态。");
}
