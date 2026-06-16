import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const queuePath = path.join(root, "inputs", "publish-queue.json");
const collectionStatusPath = path.join(root, "outputs", "collection-api-status.json");
const socialStatusPath = path.join(root, "outputs", "collection-social-assistant-status.json");
const inboxStatusPath = path.join(root, "outputs", "collection-inbox-status.json");
const roleDraftsPath = path.join(root, "outputs", "role-based-post-drafts.json");
const courseDraftsPath = path.join(root, "outputs", "course-precision-post-drafts.json");
const visualPackagePath = path.join(root, "outputs", "visual-package.json");
const visualManifestPath = path.join(root, "outputs", "visual-images", "manifest.json");
const rolePublishPath = path.join(root, "outputs", "role-publish-ready.json");
const outputPath = path.join(root, "outputs", "wechat-daily-digest.txt");
const markdownPath = path.join(root, "outputs", "wechat-daily-digest.md");

const queue = JSON.parse(fs.readFileSync(queuePath, "utf8"));

if (!Array.isArray(queue)) {
  throw new Error("inputs/publish-queue.json 必须是数组。");
}

const roleNames = {
  student: "学生号",
  ip: "IP号",
  business: "业务号"
};

const funnelNames = {
  upstream: "上游词",
  midstream: "中游词",
  downstream: "下游词"
};

const readBody = (item) => {
  if (!item.bodySource) {
    return item.body || "";
  }

  const sourcePath = path.join(root, item.bodySource);
  if (!fs.existsSync(sourcePath)) {
    return item.body || "";
  }

  const source = fs.readFileSync(sourcePath, "utf8");
  const marker = "## 正文草稿";
  const index = source.indexOf(marker);
  const body = index === -1
    ? source
    : source.slice(index + marker.length).split("\n## ")[0];

  return body.trim();
};

const preview = (text, limit = 180) => {
  const compact = text.replace(/\n{2,}/g, "\n").trim();
  return compact.length > limit ? `${compact.slice(0, limit)}...` : compact;
};

const pendingItems = queue.filter((item) => item.status !== "published");
const generatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
const collectionStatus = fs.existsSync(collectionStatusPath)
  ? JSON.parse(fs.readFileSync(collectionStatusPath, "utf8"))
  : null;
const socialStatus = fs.existsSync(socialStatusPath)
  ? JSON.parse(fs.readFileSync(socialStatusPath, "utf8"))
  : null;
const inboxStatus = fs.existsSync(inboxStatusPath)
  ? JSON.parse(fs.readFileSync(inboxStatusPath, "utf8"))
  : null;
const roleDrafts = fs.existsSync(roleDraftsPath)
  ? JSON.parse(fs.readFileSync(roleDraftsPath, "utf8"))
  : null;
const courseDrafts = fs.existsSync(courseDraftsPath)
  ? JSON.parse(fs.readFileSync(courseDraftsPath, "utf8"))
  : null;
const visualPackage = fs.existsSync(visualPackagePath)
  ? JSON.parse(fs.readFileSync(visualPackagePath, "utf8"))
  : null;
const visualManifest = fs.existsSync(visualManifestPath)
  ? JSON.parse(fs.readFileSync(visualManifestPath, "utf8"))
  : null;
const rolePublish = fs.existsSync(rolePublishPath)
  ? JSON.parse(fs.readFileSync(rolePublishPath, "utf8"))
  : null;
const blockedKeywords = collectionStatus?.results?.filter((item) => !item.ok) || [];

const lines = [
  "小红书今日待确认",
  `生成时间：${generatedAt}`,
  `社媒助手爆款：${socialStatus ? `筛选${socialStatus.parsedCount}条，新增${socialStatus.addedCount}条，热帖库${socialStatus.hotpostsTotal}条` : "未运行"}`,
  `三账号草稿：${roleDrafts ? `${roleDrafts.drafts.filter((item) => item.status === "ready").length}条已生成` : "未运行"}`,
  `课程精细化草稿：${courseDrafts ? `${courseDrafts.draftCount}条 / ${courseDrafts.courseCount}门课` : "未运行"}`,
  `图片发布包：${visualPackage ? `${visualPackage.visuals.length}套方案，${visualManifest ? `${visualManifest.count}张PNG` : "PNG未渲染"}` : "未运行"}`,
  `三账号发布包：${rolePublish ? `${rolePublish.items.length}条待确认` : "未运行"}`,
  `Inbox采集：${inboxStatus ? `解析${inboxStatus.parsedCount}条，新增${inboxStatus.addedCount}条` : "未运行"}`,
  `网页/API采集：${collectionStatus ? `${collectionStatus.collectedCount}条结构化结果` : "未运行"}`,
  blockedKeywords.length
    ? `采集提示：${blockedKeywords[0].platformMessage || "平台未返回结构化数据"}`
    : "采集提示：正常",
  `待确认：${pendingItems.length}条`,
  "",
  ...(roleDrafts?.drafts?.length
    ? [
        "三账号今日草稿：",
        ...roleDrafts.drafts
          .filter((item) => item.status === "ready")
          .map((item) => `- ${item.roleName}：${item.titleCandidates[0]}${item.precision?.status === "missing" ? "（待补课程精细化）" : ""}`),
        ""
      ]
    : []),
  ...(courseDrafts?.drafts?.length
    ? [
        "课程作业精细化草稿：",
        ...courseDrafts.drafts
          .slice(0, 6)
          .map((item) => `- ${item.roleName}｜${compact(item.course.label, 28)}：${item.titleOptions[0]}`),
        courseDrafts.drafts.length > 6 ? `- 还有 ${courseDrafts.drafts.length - 6} 条，见 outputs/course-precision-post-drafts.md` : "",
        "完整课程精细化草稿：outputs/course-precision-post-drafts.md",
        ""
      ].filter(Boolean)
    : []),
  ...(visualPackage?.visuals?.length
    ? [
        "图片今日要做：",
        ...visualPackage.visuals.map((item) => `- ${item.roleName}：${String(item.coverText).replace(/\n/g, " / ")}`),
        visualManifest ? `PNG目录：${visualManifest.outputDir}` : "PNG目录：未生成",
        visualManifest?.contactSheet ? `图片总览：${visualManifest.contactSheet}` : "",
        ""
      ]
    : []),
  ...(rolePublish?.items?.length
    ? [
        "三账号发布包：",
        ...rolePublish.items.map((item) => `- ${item.accountName}：${item.title}`),
        "完整三账号发布包：outputs/role-publish-ready.md",
        ""
      ]
    : []),
  ...pendingItems.flatMap((item, index) => {
    const body = readBody(item);
    return [
      `${index + 1}. ${item.title || "未命名标题"}`,
      `账号：${item.accountName || "未填写"} / ${roleNames[item.accountRole] || item.accountRole || "未填写"}`,
      `阶段：${funnelNames[item.searchFunnel] || item.searchFunnel || "未填写"}`,
      `时间：${item.scheduledAt || "未填写"}`,
      `封面：${item.coverIdea || "未填写"}`,
      `标签：${item.hashtags?.length ? item.hashtags.map((tag) => `#${tag}`).join(" ") : "未填写"}`,
      "正文预览：",
      preview(body) || "未填写正文",
      "确认项：",
      ...(item.prePublishChecks || []).slice(0, 5).map((check) => `- ${check}`),
      "- 人工确认可以对外发布",
      ""
    ];
  }),
  pendingItems.length ? "完整发布包见 outputs/publish-ready.md" : "暂无待确认内容。",
  "注意：这条消息只用于手机查看和确认，不自动发布。"
];

const text = lines.join("\n");
const markdown = [
  "# 小红书今日待确认",
  "",
  ...lines.slice(1)
].join("\n");

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, text);
fs.writeFileSync(markdownPath, markdown);

console.log(`已生成 ${outputPath}`);
console.log(`已生成 ${markdownPath}`);
