import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "./load-env.mjs";
import { mergeHotposts, normalizeHotpost, readJsonArray, toNumber } from "./hotpost-utils.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const defaultPython = "/Users/meilucia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const defaultSourceDir = "/Users/meilucia/Downloads/社媒助手";

const sourceDir = process.env.SOCIAL_ASSISTANT_DIR || defaultSourceDir;
const pythonBin = process.env.XHS_PYTHON_BIN || (fs.existsSync(defaultPython) ? defaultPython : "python3");
const maxPerFile = toNumber(process.env.SOCIAL_ASSISTANT_MAX_PER_FILE || 30);
const maxPerRole = toNumber(process.env.SOCIAL_ASSISTANT_MAX_PER_ROLE || 10);
const minTotalEngagement = toNumber(process.env.SOCIAL_ASSISTANT_MIN_TOTAL || 50);

const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const statusPath = path.join(root, "outputs", "collection-social-assistant-status.json");
const reportPath = path.join(root, "outputs", "collection-social-assistant-status.md");
const roleHotpostsPath = path.join(root, "outputs", "social-assistant-role-hotposts.json");

const supported = new Set([".xlsx", ".xlsm", ".csv"]);

const walk = (dir) => {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(fullPath);
    if (!entry.isFile()) return [];
    if (entry.name.startsWith("~$")) return [];
    return supported.has(path.extname(entry.name).toLowerCase()) ? [fullPath] : [];
  });
};

const extractKeyword = (filePath) => {
  const base = path.basename(filePath, path.extname(filePath));
  const quoted = base.match(/「([^」]+)」/);
  if (quoted) return quoted[1].trim();
  return base.replace(/^【社媒助手】/, "").replace(/-\d{8}-\d{4}$/, "").trim();
};

const pyCode = String.raw`
import csv
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
suffix = path.suffix.lower()

def clean(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).strip()

if suffix == ".csv":
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
else:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    values = list(ws.iter_rows(values_only=True))
    if not values:
        rows = []
    else:
        headers = [clean(v) for v in values[0]]
        rows = []
        for line in values[1:]:
            item = {}
            for idx, header in enumerate(headers):
                if header:
                    item[header] = clean(line[idx] if idx < len(line) else "")
            rows.append(item)

print(json.dumps(rows, ensure_ascii=False))
`;

const readRows = (filePath) => {
  const result = spawnSync(pythonBin, ["-c", pyCode, filePath], {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024
  });

  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "表格读取失败").trim());
  }

  return JSON.parse(result.stdout || "[]");
};

const valueOf = (row, names) => {
  for (const name of names) {
    if (row[name] !== undefined && row[name] !== "") return row[name];
  }
  return "";
};

const inferFunnel = (title, content) => {
  const text = `${title} ${content}`.toLowerCase();
  if (/急|ddl|deadline|due|还有|明天|考试|final|挂科|补救|辅导|找老师|改/.test(text)) return "downstream";
  if (/攻略|避坑|怎么|如何|流程|申请|准备|时间线|经验/.test(text)) return "midstream";
  return "upstream";
};

const inferRole = (title, content) => {
  const text = `${title} ${content}`;
  if (/辅导|机构|老师|服务|咨询|规划|试听|案例/.test(text)) return "business";
  if (/我|本人|留子|英硕|作业|essay|dissertation|final|考试/.test(text)) return "student";
  return "ip";
};

const roleSignals = {
  student: {
    funnel: "upstream",
    include: /我|本人|留子|英硕|崩溃|焦虑|哭|救命|怎么办|final|考试|作业|essay|dissertation|ddl|学不完|复习|挂科/i,
    exclude: /辅导|机构|服务|咨询|私信|老师带|报价|试听/i,
    score: ({ likes, comments, favorites, shares, text }) =>
      Math.sqrt(likes + comments + favorites + shares) * 120 + comments * 2.2 + (/(救命|崩溃|哭|怎么办|学不完|无从下手|急)/.test(text) ? 700 : 0)
  },
  ip: {
    funnel: "midstream",
    include: /攻略|经验|方法|秘诀|避坑|复盘|如何|怎么|流程|建议|准备|复习|参考|总结/i,
    exclude: /私信|加我|报价|下单|接单/i,
    score: ({ likes, comments, favorites, shares, text }) =>
      Math.sqrt(likes + comments + favorites + shares) * 120 + favorites * 1.8 + shares * 1.4 + (/(攻略|经验|方法|秘诀|避坑|复盘|如何|怎么)/.test(text) ? 900 : 0)
  },
  business: {
    funnel: "downstream",
    include: /辅导|求助|风险|挂|分数|成绩|案例|AI率|essay|dissertation|report|proposal|ddl|补救|改|老师|课程/i,
    exclude: /朋友圈|纯吐槽|日常vlog/i,
    score: ({ likes, comments, favorites, shares, text }) =>
      Math.sqrt(likes + comments + favorites + shares) * 120 + comments * 2 + favorites * 1.4 + (/(辅导|求助|风险|补救|AI率|essay|dissertation|案例|改)/i.test(text) ? 950 : 0)
  }
};

const roleFit = ({ title, content, likes, comments, favorites, shares }, role) => {
  const signal = roleSignals[role];
  const text = `${title} ${content}`;
  const includeBonus = signal.include.test(text) ? 1 : 0;
  const excludePenalty = signal.exclude.test(text) ? 0.45 : 1;
  const base = signal.score({ likes, comments, favorites, shares, text });
  return Math.round((base + includeBonus * 1000) * excludePenalty);
};

const normalizeRow = (row, defaults) => {
  const title = valueOf(row, ["笔记标题", "标题", "title", "display_title"]);
  const content = valueOf(row, ["笔记内容", "内容", "正文", "desc", "description"]);
  const url = valueOf(row, ["笔记链接", "链接", "url", "noteUrl"]);
  const author = valueOf(row, ["博主昵称", "作者", "账号", "nickname", "author"]);
  const noteId = valueOf(row, ["笔记ID", "noteId", "id"]);
  const likes = toNumber(valueOf(row, ["点赞量", "点赞", "likes", "likeCount"]));
  const favorites = toNumber(valueOf(row, ["收藏量", "收藏", "favorites", "collectCount"]));
  const comments = toNumber(valueOf(row, ["评论量", "评论", "comments", "commentCount"]));
  const shares = toNumber(valueOf(row, ["分享量", "分享", "shares", "shareCount"]));
  const totalEngagement = likes + favorites + comments + shares;
  const hotScore = likes + favorites * 1.5 + comments * 2 + shares * 1.2;
  const safeTitle = title || content.slice(0, 40) || noteId || "未命名社媒助手笔记";

  const baseHotpost = normalizeHotpost(
    {
      title: safeTitle,
      url,
      authorType: author || "小红书作者",
      likes,
      comments,
      favorites,
      accountRole: inferRole(safeTitle, content),
      searchFunnel: inferFunnel(safeTitle, content),
      longTailKeyword: defaults.keyword || safeTitle,
      topic: defaults.keyword || safeTitle,
      hook: safeTitle,
      notes: [
        `来源：社媒助手表格 ${defaults.file}`,
        `关键词：${defaults.keyword || "未识别"}`,
        `热度分：${hotScore.toFixed(1)}`,
        `总互动：${totalEngagement}`,
        `分享：${shares}`,
        noteId ? `笔记ID：${noteId}` : ""
      ].filter(Boolean).join("；")
    },
    defaults
  );

  return {
    raw: row,
    content,
    shares,
    totalEngagement,
    hotScore,
    roleScores: {
      student: roleFit({ title: safeTitle, content, likes, comments, favorites, shares }, "student"),
      ip: roleFit({ title: safeTitle, content, likes, comments, favorites, shares }, "ip"),
      business: roleFit({ title: safeTitle, content, likes, comments, favorites, shares }, "business")
    },
    hotpost: baseHotpost
  };
};

const files = walk(sourceDir);
const parsedByFile = [];
const roleBuckets = {
  student: [],
  ip: [],
  business: []
};

for (const filePath of files) {
  const keyword = extractKeyword(filePath);
  const file = path.relative(sourceDir, filePath);

  try {
    const rows = readRows(filePath);
    const ranked = rows
      .map((row) => normalizeRow(row, { keyword, file }))
      .filter((item) => item.hotpost.title && (item.hotpost.url || item.hotpost.title))
      .sort((a, b) => b.hotScore - a.hotScore);

    const eligible = ranked.filter((item) => item.totalEngagement >= minTotalEngagement);
    const selected = (eligible.length ? eligible : ranked).slice(0, maxPerFile);
    const roleSelected = Object.fromEntries(
      Object.keys(roleBuckets).map((role) => {
        const signal = roleSignals[role];
        const eligibleForRole = ranked.filter((item) => {
          const text = `${item.hotpost.title} ${item.content}`;
          return signal.include.test(text) && !signal.exclude.test(text);
        });
        const source = eligibleForRole.length ? eligibleForRole : ranked;
        const items = source
          .filter((item) => item.totalEngagement >= minTotalEngagement || source.length <= maxPerRole)
          .map((item) => ({
            ...item,
            roleScore: item.roleScores[role],
            hotpost: {
              ...item.hotpost,
              accountRole: role,
              searchFunnel: roleSignals[role].funnel,
              sourceContent: item.content,
              notes: `${item.hotpost.notes}；账号SOP：${role}；角色匹配分：${item.roleScores[role]}`
            }
          }))
          .sort((a, b) => b.roleScore - a.roleScore)
          .slice(0, maxPerRole);

        roleBuckets[role].push(...items.map((item) => item.hotpost));
        return [role, items.length];
      })
    );

    parsedByFile.push({
      file,
      ok: true,
      keyword,
      rowCount: rows.length,
      selectedCount: selected.length,
      roleSelected,
      topScore: selected[0]?.hotScore || 0,
      topTitle: selected[0]?.hotpost.title || "",
      items: selected.map((item) => item.hotpost)
    });
  } catch (error) {
    parsedByFile.push({
      file,
      ok: false,
      keyword,
      rowCount: 0,
      selectedCount: 0,
      error: error.message,
      items: []
    });
  }
}

const incoming = parsedByFile.flatMap((item) => item.items);
const mergeResult = incoming.length
  ? mergeHotposts(hotpostsPath, incoming)
  : { total: readJsonArray(hotpostsPath).length, added: 0 };

const status = {
  generatedAt: new Date().toISOString(),
  sourceDir,
  fileCount: files.length,
  parsedCount: incoming.length,
  addedCount: mergeResult.added,
  hotpostsTotal: mergeResult.total,
  rules: {
    maxPerFile,
    maxPerRole,
    minTotalEngagement,
    hotScore: "likes + favorites*1.5 + comments*2 + shares*1.2",
    roleScore: "按学生号/IP号/业务号 SOP 关键词、搜索阶段、互动结构分别加权"
  },
  roleBuckets: Object.fromEntries(
    Object.entries(roleBuckets).map(([role, items]) => [role, {
      count: items.length,
      topTitles: items.slice(0, 5).map((item) => item.title)
    }])
  ),
  files: parsedByFile.map(({ items, ...item }) => item)
};

const report = [
  "# 社媒助手爆款表格采集",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `扫描目录：${sourceDir}`,
  `表格数量：${files.length}`,
  `筛选入围：${incoming.length}`,
  `新增入库：${mergeResult.added}`,
  `热帖库总数：${mergeResult.total}`,
  "",
  "## 筛选规则",
  "",
  `- 单表最多：${maxPerFile} 条`,
  `- 每个账号类型最多：${maxPerRole} 条`,
  `- 默认总互动门槛：${minTotalEngagement}`,
  "- 热度分：点赞 + 收藏*1.5 + 评论*2 + 分享*1.2",
  "- 角色匹配：学生号看情绪/求助/IP号看方法/经验/业务号看明确需求/案例。",
  "- 如果某个表没有达到门槛的内容，会自动取该表热度分最高的内容，避免空跑。",
  "",
  "## 按账号 SOP 的爆帖池",
  "",
  ...Object.entries(roleBuckets).flatMap(([role, items]) => [
    `### ${role}`,
    "",
    ...(items.length
      ? items.slice(0, 5).map((item, index) => `${index + 1}. ${item.title}（赞${item.likes} / 评${item.comments} / 藏${item.favorites}）`)
      : ["- 暂无"]),
    ""
  ]),
  "",
  "## 文件结果",
  "",
  ...(parsedByFile.length
    ? parsedByFile.map((item) => {
        const suffix = item.ok
          ? `行数 ${item.rowCount}，入围 ${item.selectedCount}，最高分 ${Number(item.topScore || 0).toFixed(1)}${item.topTitle ? `，Top：${item.topTitle}` : ""}`
          : `失败：${item.error}`;
        return `- ${item.ok ? "OK" : "FAIL"} ${item.file}：${suffix}`;
      })
    : ["- 未找到表格文件"]),
  "",
  "## 使用方式",
  "",
  "把社媒助手导出的表格放进：",
  "",
  "```text",
  sourceDir,
  "```",
  "",
  "然后运行：",
  "",
  "```bash",
  "npm run collect:social",
  "```",
  "",
  "总控 `npm run control` 会自动执行这一步。"
].join("\n");

fs.mkdirSync(path.dirname(statusPath), { recursive: true });
fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
fs.writeFileSync(reportPath, report);
fs.writeFileSync(roleHotpostsPath, JSON.stringify(roleBuckets, null, 2));

console.log(`已生成 ${statusPath}`);
console.log(`已生成 ${reportPath}`);
console.log(`已生成 ${roleHotpostsPath}`);
console.log(`社媒助手表格筛选 ${incoming.length} 条，新增 ${mergeResult.added} 条，热帖库共 ${mergeResult.total} 条。`);
