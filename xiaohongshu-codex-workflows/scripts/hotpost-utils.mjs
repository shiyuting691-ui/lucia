import fs from "node:fs";
import path from "node:path";

export const readJsonArray = (filePath) => {
  if (!fs.existsSync(filePath)) return [];
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  return Array.isArray(value) ? value : [];
};

export const toNumber = (value) => {
  if (typeof value === "number") return value;
  if (!value) return 0;
  const text = String(value).trim();
  if (text.endsWith("万")) return Math.round(Number(text.slice(0, -1)) * 10000);
  const parsed = Number(text.replace(/[^\d.]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
};

export const normalizeHotpost = (item, defaults = {}) => {
  const title = item.title || item.display_title || item.displayTitle || item.noteTitle || "";
  const url = item.url || item.link || item.noteUrl || "";
  const keyword = item.longTailKeyword || item.keyword || defaults.keyword || title;

  return {
    title: title || keyword || "未命名热帖",
    url,
    accountRole: item.accountRole || defaults.accountRole || defaults.accountRoleHint || "ip",
    searchFunnel: item.searchFunnel || defaults.searchFunnel || defaults.searchFunnelHint || "midstream",
    authorType: item.authorType || item.author || item.nickname || "小红书作者",
    likes: toNumber(item.likes || item.likeCount || item.liked_count),
    comments: toNumber(item.comments || item.commentCount || item.comment_count),
    favorites: toNumber(item.favorites || item.collectCount || item.collected_count),
    topic: item.topic || defaults.topic || keyword || "小红书热帖",
    audience: item.audience || defaults.audience || "目标小红书搜索用户",
    longTailKeyword: keyword || title,
    hook: item.hook || title || keyword,
    structure: Array.isArray(item.structure)
      ? item.structure
      : ["标题先给具体痛点", "正文补充真实场景", "结尾开放评论问题"],
    tone: Array.isArray(item.tone) ? item.tone : ["真实", "搜索友好"],
    commentTrigger: item.commentTrigger || "你现在卡在哪一步",
    cta: item.cta || "评论区说具体情况",
    notes: item.notes || defaults.notes || "由采集导入层补充。"
  };
};

export const mergeHotposts = (hotpostsPath, incoming) => {
  const existing = readJsonArray(hotpostsPath);
  const seen = new Set(existing.map((item) => item.url || item.title));
  const merged = [...existing];
  let added = 0;

  for (const item of incoming) {
    const key = item.url || item.title;
    if (!key || seen.has(key)) continue;
    merged.push(item);
    seen.add(key);
    added += 1;
  }

  fs.mkdirSync(path.dirname(hotpostsPath), { recursive: true });
  fs.writeFileSync(hotpostsPath, JSON.stringify(merged, null, 2));
  return { total: merged.length, added };
};
