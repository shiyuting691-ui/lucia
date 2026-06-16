import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { loadEnvFile } from "./load-env.mjs";
import { mergeHotposts, normalizeHotpost, readJsonArray, toNumber } from "./hotpost-utils.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const outputDir = path.join(root, "outputs");
const hotpostsPath = path.join(root, "inputs", "hotposts.json");
const courseContextPath = path.join(root, "inputs", "course-context.json");
const courseBankPath = path.join(outputDir, "course-context-bank.json");
const statusPath = path.join(outputDir, "collection-lark-sheets-status.json");
const reportPath = path.join(outputDir, "collection-lark-sheets-status.md");
const defaultRange = process.env.LARK_SHEET_RANGE?.trim() || "A1:Z300";
const defaultPython = "/Users/meilucia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const pythonBin = process.env.XHS_PYTHON_BIN || (fs.existsSync(defaultPython) ? defaultPython : "python3");
const localExportDir = process.env.LARK_LOCAL_EXPORT_DIR || path.join(root, "inputs", "lark-course-sheets");

const appId = process.env.LARK_APP_ID?.trim();
const appSecret = process.env.LARK_APP_SECRET?.trim();
const supportedLocalFiles = new Set([".xlsx", ".xlsm", ".csv"]);

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

const writeOutputs = (status, reportLines) => {
  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(statusPath, JSON.stringify(status, null, 2));
  fs.writeFileSync(reportPath, reportLines.join("\n"));
};

const emptyCourseContext = () => ({
  enabled: false,
  university: "",
  courseCode: "",
  courseTitle: "",
  academicYear: "",
  studentStage: "",
  assessment: {
    type: "",
    weight: "",
    deliverable: "",
    deadline: "",
    rubricFocus: []
  },
  studentNeed: "",
  officialSources: []
});

const resetCourseContext = () => {
  fs.mkdirSync(path.dirname(courseContextPath), { recursive: true });
  fs.writeFileSync(courseBankPath, JSON.stringify([], null, 2));
  fs.writeFileSync(courseContextPath, JSON.stringify(emptyCourseContext(), null, 2));
};

const parseSpreadsheetToken = (value) => {
  const text = String(value || "").trim();
  if (!text) return "";
  const match = text.match(/\/sheets\/([A-Za-z0-9]+)/);
  if (match) return match[1];
  return text.replace(/[?#].*$/, "");
};

const parseSources = () => {
  if (process.env.LARK_FILE_SOURCES_JSON?.trim()) {
    const parsed = JSON.parse(process.env.LARK_FILE_SOURCES_JSON);
    const sources = Array.isArray(parsed) ? parsed : [parsed];
    return sources
      .map((source, index) => ({
        name: source.name || `飞书表格 ${index + 1}`,
        spreadsheetToken: parseSpreadsheetToken(source.spreadsheetToken || source.token || source.url),
        range: source.range || defaultRange,
        accountRole: source.accountRole,
        searchFunnel: source.searchFunnel,
        topic: source.topic,
        keyword: source.keyword
      }))
      .filter((source) => source.spreadsheetToken);
  }

  const urls = (process.env.LARK_SHEET_URLS || process.env.LARK_SHEET_URL || process.env.LARK_SPREADSHEET_TOKEN || "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);

  return urls.map((url, index) => ({
    name: `飞书表格 ${index + 1}`,
    spreadsheetToken: parseSpreadsheetToken(url),
    range: defaultRange
  }));
};

const walkLocalExports = (dir) => {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return walkLocalExports(fullPath);
    if (!entry.isFile()) return [];
    if (entry.name.startsWith("~$")) return [];
    return supportedLocalFiles.has(path.extname(entry.name).toLowerCase()) ? [fullPath] : [];
  });
};

const readLocalRows = (filePath) => {
  const result = spawnSync(pythonBin, ["-c", pyCode, filePath], {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024
  });

  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "飞书导出表格读取失败").trim());
  }

  return JSON.parse(result.stdout || "[]");
};

const readLocalSources = () =>
  walkLocalExports(localExportDir).map((filePath, index) => ({
    name: path.basename(filePath, path.extname(filePath)) || `飞书导出表格 ${index + 1}`,
    filePath,
    range: "local-export"
  }));

const valueOf = (row, names) => {
  for (const name of names) {
    if (row[name] !== undefined && row[name] !== "") return row[name];
  }
  return "";
};

const inferFunnel = (title, content) => {
  const text = `${title} ${content}`.toLowerCase();
  if (/急|ddl|deadline|due|明天|考试|final|挂科|补救|改|ai率|turnitin/.test(text)) return "downstream";
  if (/攻略|避坑|怎么|如何|流程|时间线|经验|方法|模板|rubric/.test(text)) return "midstream";
  return "upstream";
};

const inferRole = (title, content) => {
  const text = `${title} ${content}`;
  if (/报价|服务|咨询|老师|案例|辅导|规划|方案/.test(text)) return "business";
  if (/我|本人|留子|作业|essay|dissertation|final|考试|ddl|崩溃|救命/.test(text)) return "student";
  return "ip";
};

const rowToObject = (headers, values) =>
  Object.fromEntries(headers.map((header, index) => [String(header || `列${index + 1}`).trim(), values[index] ?? ""]));

const normalizeRow = (row, source) => {
  const title = valueOf(row, ["笔记标题", "标题", "title", "Title", "选题", "主题", "hook", "Hook"]);
  const content = valueOf(row, ["笔记内容", "内容", "正文", "desc", "description", "文案", "素材", "痛点"]);
  const url = valueOf(row, ["笔记链接", "链接", "url", "URL", "noteUrl"]);
  const author = valueOf(row, ["博主昵称", "作者", "账号", "nickname", "author"]);
  const likes = toNumber(valueOf(row, ["点赞量", "点赞", "likes", "likeCount"]));
  const favorites = toNumber(valueOf(row, ["收藏量", "收藏", "favorites", "collectCount"]));
  const comments = toNumber(valueOf(row, ["评论量", "评论", "comments", "commentCount"]));
  const shares = toNumber(valueOf(row, ["分享量", "分享", "shares", "shareCount"]));
  const keyword = valueOf(row, ["关键词", "搜索词", "keyword", "longTailKeyword"]) || source.keyword || title || "飞书素材";
  const safeTitle = String(title || content || keyword || "").slice(0, 80);

  if (!safeTitle) return null;

  return normalizeHotpost(
    {
      title: safeTitle,
      url,
      accountRole: source.accountRole || inferRole(safeTitle, content),
      searchFunnel: source.searchFunnel || inferFunnel(safeTitle, content),
      authorType: author || "飞书素材",
      likes,
      comments,
      favorites,
      topic: source.topic || keyword,
      audience: valueOf(row, ["目标人群", "受众", "audience"]) || "目标小红书搜索用户",
      longTailKeyword: keyword,
      hook: valueOf(row, ["钩子", "hook", "Hook"]) || safeTitle,
      notes: [
        `来源：飞书表格 ${source.name}`,
        `读取范围：${source.range}`,
        shares ? `分享：${shares}` : "",
        content ? `原始内容：${String(content).slice(0, 180)}` : ""
      ].filter(Boolean).join("；")
    },
    {
      keyword,
      topic: source.topic || keyword
    }
  );
};

const firstValue = (row, names) => String(valueOf(row, names) || "").trim();

const splitList = (value) =>
  String(value || "")
    .split(/[;；,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);

const normalizeCourseRow = (row, source) => {
  const university = firstValue(row, ["学校", "大学", "University", "university", "院校"]);
  const courseCode = firstValue(row, ["课程代码", "Course Code", "courseCode", "module code", "Module Code", "代码"]);
  const courseTitle = firstValue(row, ["课程名称", "课程", "Course", "course", "Module Title", "module title", "Module"]);
  const assessmentType = firstValue(row, ["评估方式", "assessment", "Assessment", "作业类型", "任务类型", "类型"]);
  const deadline = firstValue(row, ["DDL", "ddl", "deadline", "Deadline", "due date", "Due Date", "截止日期"]);
  const deliverable = firstValue(row, ["交付物", "deliverable", "Deliverable", "提交内容", "作业要求", "brief"]);
  const weight = firstValue(row, ["占比", "权重", "weight", "Weight", "percentage", "Percentage"]);
  const rubric = firstValue(row, ["rubric", "Rubric", "评分标准", "评分点", "评分维度", "criteria", "Criteria"]);
  const studentNeed = firstValue(row, ["学生需求", "下一步需求", "卡点", "痛点", "studentNeed", "next step", "Next Step"]);
  const sourceUrl = firstValue(row, ["官网链接", "官方链接", "source", "Source", "url", "URL", "链接"]);
  const academicYear = firstValue(row, ["学年", "academicYear", "Academic Year", "year", "Year"]);
  const stage = firstValue(row, ["阶段", "studentStage", "Stage", "进度"]);

  const hasCourseSignal = Boolean(
    university || courseCode || courseTitle || assessmentType || deadline || deliverable || rubric || studentNeed
  );
  if (!hasCourseSignal) return null;

  return {
    enabled: true,
    sourceName: source.name,
    university,
    courseCode,
    courseTitle,
    academicYear,
    studentStage: stage || inferFunnel(`${courseCode} ${courseTitle}`, `${assessmentType} ${deadline} ${studentNeed}`),
    assessment: {
      type: assessmentType,
      weight,
      deliverable,
      deadline,
      rubricFocus: splitList(rubric).slice(0, 8)
    },
    studentNeed,
    officialSources: sourceUrl
      ? [
          {
            title: `${courseCode || courseTitle || "课程"} 官方/资料来源`,
            url: sourceUrl,
            accessedAt: new Date().toISOString().slice(0, 10)
          }
        ]
      : [],
    notes: [
      `来源：飞书表格 ${source.name}`,
      source.range ? `读取范围：${source.range}` : "",
      !sourceUrl ? "未提供官网/官方文件链接，发布前不要写死未验证事实。" : ""
    ].filter(Boolean)
  };
};

const courseScore = (course) => {
  let score = 0;
  if (course.university) score += 2;
  if (course.courseCode) score += 4;
  if (course.courseTitle) score += 3;
  if (course.assessment?.type) score += 3;
  if (course.assessment?.deadline) score += 4;
  if (course.assessment?.weight) score += 2;
  if (course.assessment?.rubricFocus?.length) score += 3;
  if (course.studentNeed) score += 3;
  if (course.officialSources?.length) score += 5;
  return score;
};

const writeCourseContext = (courses) => {
  fs.mkdirSync(path.dirname(courseContextPath), { recursive: true });
  fs.writeFileSync(courseBankPath, JSON.stringify(courses, null, 2));

  if (!courses.length) {
    fs.writeFileSync(courseContextPath, JSON.stringify(emptyCourseContext(), null, 2));
    return null;
  }

  const selected = [...courses].sort((a, b) => courseScore(b) - courseScore(a))[0];
  fs.writeFileSync(courseContextPath, JSON.stringify(selected, null, 2));
  return selected;
};

const requestJson = async (url, options = {}) => {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.code !== 0) {
    throw new Error(`HTTP ${response.status} ${JSON.stringify(body)}`);
  }
  return body;
};

const getTenantAccessToken = async () => {
  const body = await requestJson("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8"
    },
    body: JSON.stringify({
      app_id: appId,
      app_secret: appSecret
    })
  });
  return body.tenant_access_token;
};

const readSheetRows = async (tenantAccessToken, source) => {
  const range = await resolveRange(tenantAccessToken, source);
  const url = `https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${encodeURIComponent(source.spreadsheetToken)}/values/${encodeURIComponent(range)}`;
  const body = await requestJson(url, {
    headers: {
      Authorization: `Bearer ${tenantAccessToken}`,
      "Content-Type": "application/json; charset=utf-8"
    }
  });

  const values = body.data?.valueRange?.values || [];
  if (!values.length) return [];

  const headers = values[0].map((item, index) => String(item || `列${index + 1}`).trim());
  return values.slice(1).map((line) => rowToObject(headers, line));
};

const querySheets = async (tenantAccessToken, spreadsheetToken) => {
  const body = await requestJson(
    `https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${encodeURIComponent(spreadsheetToken)}/sheets/query`,
    {
      headers: {
        Authorization: `Bearer ${tenantAccessToken}`,
        "Content-Type": "application/json; charset=utf-8"
      }
    }
  );
  return body.data?.sheets || [];
};

const resolveRange = async (tenantAccessToken, source) => {
  if (source.range.includes("!")) return source.range;

  const sheets = await querySheets(tenantAccessToken, source.spreadsheetToken);
  const firstSheetId = sheets[0]?.sheet_id;
  if (!firstSheetId) return source.range;

  return `${firstSheetId}!${source.range}`;
};

const sources = parseSources();
const localSources = readLocalSources();
const missing = [
  !sources.length && !localSources.length ? "LARK_SHEET_URLS / LARK_FILE_SOURCES_JSON / 本地飞书导出表格" : "",
  sources.length && !localSources.length && !appId ? "LARK_APP_ID" : "",
  sources.length && !localSources.length && !appSecret ? "LARK_APP_SECRET" : ""
].filter(Boolean);

if (missing.length) {
  resetCourseContext();
  const status = {
    generatedAt: new Date().toISOString(),
    ok: false,
    skipped: true,
    missing,
    importedCount: 0,
    courseContextCount: 0,
    addedCount: 0,
    hotpostsTotal: readJsonArray(hotpostsPath).length,
    localExportDir
  };
  writeOutputs(status, [
    "# 飞书表格采集状态",
    "",
    `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
    `状态：已跳过，缺少 ${missing.join("、")}`,
    "",
    "## 需要配置",
    "",
    "- API方式：配置 `LARK_APP_ID`、`LARK_APP_SECRET`、`LARK_SHEET_URLS`。",
    `- 导出方式：把飞书表格导出的 .xlsx/.csv 放入 \`${path.relative(root, localExportDir)}\`。`,
    "- `LARK_SHEET_RANGE`：API读取范围，默认 `A1:Z300`。"
  ]);
  console.log(`飞书表格采集已跳过：缺少 ${missing.join("、")}`);
  process.exit(0);
}

const parsedSources = [];
let normalized = [];
let courseContexts = [];

try {
  for (const source of localSources) {
    try {
      const rows = readLocalRows(source.filePath);
      const items = rows.map((row) => normalizeRow(row, source)).filter(Boolean);
      const courses = rows.map((row) => normalizeCourseRow(row, source)).filter(Boolean);
      normalized.push(...items);
      courseContexts.push(...courses);
      parsedSources.push({
        ...source,
        ok: true,
        sourceType: "local-export",
        file: path.relative(root, source.filePath),
        rowCount: rows.length,
        importedCount: items.length,
        courseContextCount: courses.length,
        topTitle: items[0]?.title || ""
      });
    } catch (error) {
      parsedSources.push({
        ...source,
        ok: false,
        sourceType: "local-export",
        file: path.relative(root, source.filePath),
        rowCount: 0,
        importedCount: 0,
        courseContextCount: 0,
        error: error.message
      });
    }
  }

  if (!sources.length) {
    throw new Error("未配置飞书 API 表格链接，已仅处理本地导出表格。");
  }

  if (!appId || !appSecret) {
    throw new Error("飞书 API 凭证未配置，已仅处理本地导出表格。");
  }

  const token = await getTenantAccessToken();

  for (const source of sources) {
    try {
      const rows = await readSheetRows(token, source);
      const items = rows.map((row) => normalizeRow(row, source)).filter(Boolean);
      const courses = rows.map((row) => normalizeCourseRow(row, source)).filter(Boolean);
      normalized.push(...items);
      courseContexts.push(...courses);
      parsedSources.push({
        ...source,
        ok: true,
        sourceType: "api",
        rowCount: rows.length,
        importedCount: items.length,
        courseContextCount: courses.length,
        topTitle: items[0]?.title || ""
      });
    } catch (error) {
      parsedSources.push({
        ...source,
        ok: false,
        sourceType: "api",
        rowCount: 0,
        importedCount: 0,
        courseContextCount: 0,
        error: error.message
      });
    }
  }
} catch (error) {
  if (sources.length || !localSources.length) {
    parsedSources.push({
      name: "飞书 API",
      ok: false,
      sourceType: "api",
      rowCount: 0,
      importedCount: 0,
      courseContextCount: 0,
      error: error.message
    });
  }
}

const mergeResult = normalized.length
  ? mergeHotposts(hotpostsPath, normalized)
  : { total: readJsonArray(hotpostsPath).length, added: 0 };
const selectedCourseContext = writeCourseContext(courseContexts);

const status = {
  generatedAt: new Date().toISOString(),
  ok: parsedSources.some((source) => source.ok),
  skipped: false,
  sourceCount: sources.length,
  localSourceCount: localSources.length,
  localExportDir,
  importedCount: normalized.length,
  courseContextCount: courseContexts.length,
  selectedCourseContext: selectedCourseContext
    ? [selectedCourseContext.university, selectedCourseContext.courseCode, selectedCourseContext.courseTitle].filter(Boolean).join(" ")
    : "",
  addedCount: mergeResult.added,
  hotpostsTotal: mergeResult.total,
  sources: parsedSources.map(({ spreadsheetToken, ...source }) => ({
    ...source,
    spreadsheetToken: spreadsheetToken ? `${spreadsheetToken.slice(0, 6)}...` : ""
  }))
};

writeOutputs(status, [
  "# 飞书表格采集状态",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `API表格数量：${sources.length}`,
  `本地导出表格：${localSources.length}（${path.relative(root, localExportDir)}）`,
  `本次标准化：${normalized.length}条`,
  `课程作业信息：${courseContexts.length}条`,
  `当前精细化课程：${selectedCourseContext ? [selectedCourseContext.university, selectedCourseContext.courseCode, selectedCourseContext.courseTitle].filter(Boolean).join(" ") || "已启用" : "未识别"}`,
  `新增合并：${mergeResult.added}条`,
  `热帖库总数：${mergeResult.total}条`,
  "",
  "## 表格明细",
  "",
  ...parsedSources.map((source) =>
    `- ${source.ok ? "OK" : "FAIL"} ${source.name}：读取 ${source.rowCount || 0} 行，导入热帖 ${source.importedCount || 0} 条，课程信息 ${source.courseContextCount || 0} 条${source.error ? `，错误：${source.error}` : ""}`
  )
]);

console.log(`已生成 ${statusPath}`);
console.log(`已生成 ${reportPath}`);
console.log(`飞书表格导入 ${normalized.length} 条，课程信息 ${courseContexts.length} 条，新增 ${mergeResult.added} 条，热帖库共 ${mergeResult.total} 条。`);
