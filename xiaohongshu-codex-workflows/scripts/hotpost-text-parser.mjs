import { normalizeHotpost, toNumber } from "./hotpost-utils.mjs";

const fieldMap = new Map([
  ["标题", "title"],
  ["title", "title"],
  ["作者", "authorType"],
  ["账号", "authorType"],
  ["author", "authorType"],
  ["点赞", "likes"],
  ["赞", "likes"],
  ["likes", "likes"],
  ["评论", "comments"],
  ["comments", "comments"],
  ["收藏", "favorites"],
  ["favorites", "favorites"],
  ["链接", "url"],
  ["url", "url"],
  ["关键词", "longTailKeyword"],
  ["长尾词", "longTailKeyword"],
  ["keyword", "longTailKeyword"],
  ["账号角色", "accountRole"],
  ["role", "accountRole"],
  ["搜索阶段", "searchFunnel"],
  ["funnel", "searchFunnel"]
]);

const looksLikeMetricLine = (line) => /^(点赞|赞|评论|收藏|likes|comments|favorites)[:：]/i.test(line);
const looksLikeFieldLine = (line) => /^([^:：]{1,12})[:：]\s*(.+)$/.test(line);
const isNoiseLine = (line) =>
  !line ||
  /^(搜索|推荐|发现|消息|我|首页|关注|登录|打开小红书|展开|收起)$/.test(line) ||
  /^https?:\/\/(?!www\.xiaohongshu\.com|xhslink\.com)/i.test(line);

const parseFieldLine = (line) => {
  const match = line.match(/^([^:：]+)[:：]\s*(.+)$/);
  if (!match) return null;
  const rawKey = match[1].trim();
  const key = fieldMap.get(rawKey.toLowerCase()) || fieldMap.get(rawKey);
  if (!key) return null;
  return { key, value: match[2].trim() };
};

export const parseStructuredBlock = (block, defaults = {}) => {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => !isNoiseLine(line));

  if (!lines.length) return null;

  if (lines[0].includes("|") || lines[0].includes("\t")) {
    const parts = lines[0]
      .split(/[|\t]/)
      .map((part) => part.trim())
      .filter(Boolean);
    if (parts.length >= 2) {
      const [title, author = "", likes = 0, comments = 0, favorites = 0, keyword = ""] = parts;
      return normalizeHotpost(
        {
          title,
          authorType: author,
          likes: toNumber(likes),
          comments: toNumber(comments),
          favorites: toNumber(favorites),
          longTailKeyword: keyword || defaults.keyword || title,
          topic: keyword || defaults.keyword || title
        },
        defaults
      );
    }
  }

  const firstField = parseFieldLine(lines[0]);
  const item = firstField?.key === "title"
    ? { title: firstField.value }
    : { title: lines[0] };

  const bodyLines = firstField?.key === "title" ? lines.slice(1) : lines.slice(1);
  for (const line of bodyLines) {
    const parsed = parseFieldLine(line);
    if (!parsed) continue;

    item[parsed.key] = ["likes", "comments", "favorites"].includes(parsed.key)
      ? toNumber(parsed.value)
      : parsed.value;
  }

  return normalizeHotpost(item, defaults);
};

export const parseLooseXhsText = (text, defaults = {}) => {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => !isNoiseLine(line));

  const posts = [];
  let current = null;

  const flush = () => {
    if (!current?.title) return;
    posts.push(
      normalizeHotpost(
        {
          ...current,
          longTailKeyword: current.longTailKeyword || defaults.keyword || current.title,
          topic: defaults.keyword || current.topic || current.title
        },
        defaults
      )
    );
    current = null;
  };

  for (const line of lines) {
    if (/^https?:\/\/(www\.xiaohongshu\.com|xhslink\.com)/i.test(line)) {
      current ||= {};
      current.url = line;
      continue;
    }

    const parsedField = parseFieldLine(line);
    if (parsedField?.key === "title") {
      if (current?.title) flush();
      current = {
        title: parsedField.value,
        authorType: defaults.authorType || "小红书作者"
      };
      continue;
    }

    if ((looksLikeMetricLine(line) || looksLikeFieldLine(line)) && current && parsedField) {
      current[parsedField.key] = ["likes", "comments", "favorites"].includes(parsedField.key)
        ? toNumber(parsedField.value)
        : parsedField.value;
      continue;
    }

    if (looksLikeFieldLine(line)) {
      continue;
    }

    if (line.length >= 6 && line.length <= 80) {
      if (current?.title) flush();
      current = {
        title: line,
        authorType: defaults.authorType || "小红书作者"
      };
    }
  }

  flush();
  return posts;
};

export const parseHotpostText = (text, defaults = {}) => {
  const blocks = text
    .split(/\n\s*\n/g)
    .map((block) => block.trim())
    .filter(Boolean);

  if (blocks.length > 1) {
    const structured = blocks.map((block) => parseStructuredBlock(block, defaults)).filter(Boolean);
    if (structured.length) return structured;
  }

  const single = parseStructuredBlock(text, defaults);
  const loose = parseLooseXhsText(text, defaults);

  if (loose.length > 1) return loose;
  return single ? [single] : loose;
};
