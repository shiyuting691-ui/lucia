import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);
const root = path.resolve(process.cwd());
const configPath = path.join(root, "inputs", "collect-keywords.json");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const shotsDir = path.join(root, "outputs", "screenshots");
const ocrOutputPath = path.join(root, "outputs", "xhs-visual-ocr.json");
const statusPath = path.join(root, "outputs", "xhs-visual-collect-status.json");

const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const keywords = Array.isArray(config.keywords) ? config.keywords : [];
const limit = Number(config.dailyLimitPerKeyword || 5);

const roleNames = {
  student: "学生号",
  ip: "IP号",
  business: "业务号"
};

const nowStamp = () => new Date().toISOString().replace(/[:.]/g, "-");
const searchUrl = (keyword) =>
  `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}&type=51`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const parseVisiblePosts = (ocrRows, keywordItem) => {
  const sorted = ocrRows
    .filter((row) => row.text && row.confidence > 0.25)
    .sort((a, b) => {
      const yDiff = b.y - a.y;
      return Math.abs(yDiff) > 0.015 ? yDiff : a.x - b.x;
    });

  const titleLike = sorted
    .map((row) => row.text.trim())
    .filter((text) => {
      if (text.length < 4) return false;
      if (/^(全部|图文|视频|用户|筛选|发现|直播|发布|通知|更多|设置|搜索|创作中心|业务合作)$/.test(text)) return false;
      if (/^(\\d+|\\d+天前|\\d{4}-\\d{2}-\\d{2})$/.test(text)) return false;
      if (/^(KCL AI率 essay|相关搜索)$/.test(text)) return false;
      return /AI|ai|KCL|essay|学术|不端|率|查|dissertation|assignment|rubric|作业|墨大|英国/i.test(text);
    });

  const uniqueTitles = [...new Set(titleLike)].slice(0, limit);

  return uniqueTitles.map((title, index) => ({
    title,
    url: searchUrl(keywordItem.keyword),
    accountRole: keywordItem.accountRoleHint || "ip",
    searchFunnel: keywordItem.searchFunnelHint || "midstream",
    authorType: roleNames[keywordItem.accountRoleHint] || "未知账号",
    likes: 0,
    comments: 0,
    favorites: 0,
    topic: keywordItem.keyword,
    audience: "英澳留学生",
    longTailKeyword: `${keywordItem.keyword} ${title}`.slice(0, 80),
    hook: "来自小红书搜索结果的可见标题",
    structure: ["搜索结果可见标题", "需人工打开详情补正文和评论区"],
    tone: ["待判断"],
    commentTrigger: "待打开详情页补充评论区高频问题",
    cta: "待判断",
    notes: `视觉OCR采集第${index + 1}条，需复核标题和互动数据。`
  }));
};

fs.mkdirSync(shotsDir, { recursive: true });

const allOcr = [];
const collected = [];

for (const keywordItem of keywords) {
  const url = searchUrl(keywordItem.keyword);
  await run("open", [url]);
  await sleep(8000);

  const screenshotPath = path.join(shotsDir, `xhs-${nowStamp()}-${keywordItem.keyword.replace(/[^a-z0-9\\u4e00-\\u9fa5]+/gi, "-")}.png`);
  await run("screencapture", ["-x", screenshotPath]);

  const { stdout } = await run("swift", ["scripts/ocr-image.swift", screenshotPath], {
    cwd: root,
    maxBuffer: 1024 * 1024 * 10
  });

  const rows = JSON.parse(stdout);
  allOcr.push({
    keyword: keywordItem.keyword,
    url,
    screenshotPath,
    rows
  });
  collected.push(...parseVisiblePosts(rows, keywordItem));
}

const existing = fs.existsSync(hotpostsPath)
  ? JSON.parse(fs.readFileSync(hotpostsPath, "utf8"))
  : [];

const seen = new Set();
const merged = [...collected, ...existing].filter((post) => {
  const key = `${post.title}|${post.url}`;
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
});

fs.writeFileSync(hotpostsPath, JSON.stringify(merged, null, 2));
fs.writeFileSync(ocrOutputPath, JSON.stringify(allOcr, null, 2));
fs.writeFileSync(
  statusPath,
  JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      keywords: keywords.length,
      collected: collected.length,
      hotpostsPath,
      ocrOutputPath,
      note: "视觉OCR采集只读取屏幕可见信息，标题和互动数据需要复核。"
    },
    null,
    2
  )
);

console.log(`已视觉采集 ${collected.length} 条候选标题`);
console.log(`已更新 ${hotpostsPath}`);
console.log(`已生成 ${ocrOutputPath}`);
console.log(`已生成 ${statusPath}`);
