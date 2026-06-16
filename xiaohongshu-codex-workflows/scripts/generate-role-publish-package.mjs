import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const draftsPath = path.join(root, "outputs", "role-based-post-drafts.json");
const manifestPath = path.join(root, "outputs", "visual-images", "manifest.json");
const outputMdPath = path.join(root, "outputs", "role-publish-ready.md");
const outputJsonPath = path.join(root, "outputs", "role-publish-ready.json");

const drafts = fs.existsSync(draftsPath)
  ? JSON.parse(fs.readFileSync(draftsPath, "utf8")).drafts || []
  : [];
const manifest = fs.existsSync(manifestPath)
  ? JSON.parse(fs.readFileSync(manifestPath, "utf8"))
  : { files: [], roleContactSheets: {}, quality: { ok: false } };

const roleFiles = (role) =>
  manifest.files
    .filter((item) => item.role === role)
    .map((item) => ({
      type: item.type,
      kind: item.kind || item.type,
      text: item.text || "",
      path: item.path
    }));

const publishItems = drafts
  .filter((draft) => draft.status === "ready")
  .map((draft) => ({
    id: `role-${draft.role}-${new Date().toISOString().slice(0, 10)}`,
    status: "pending_approval",
    accountRole: draft.role,
    accountName: draft.roleName,
    title: draft.titleCandidates[0],
    titleOptions: draft.titleCandidates,
    body: draft.body,
    hashtags: draft.hashtags,
    coverText: draft.visualPlan.coverText,
    visualSignal: draft.visualPlan.signals?.primary || "unknown",
    visualSignals: draft.visualPlan.signals?.matched || [],
    sourceTitle: draft.sourceTitle,
    sourceUrl: draft.sourceUrl,
    sourceMetrics: draft.sourceMetrics,
    precisionStatus: draft.precision,
    imageFiles: roleFiles(draft.role),
    contactSheet: manifest.roleContactSheets?.[draft.role] || "",
    checks: [
      ...draft.checks,
      "图片不放联系方式或硬引流",
      "截图/课程信息已打码",
      "人工确认标题、正文、图片、标签可发布"
    ]
  }));

const markdown = [
  "# 三账号今日发布包",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `图片质检：${manifest.quality?.ok ? "通过" : "需检查"}`,
  `图片总览：${manifest.contactSheet || "未生成"}`,
  "",
  "> 这个文件是发帖前确认用，不会自动发布到小红书。",
  "",
  ...publishItems.flatMap((item, index) => [
    `## ${index + 1}. ${item.accountName}`,
    "",
    `- 状态：${item.status}`,
    `- 标题：${item.title}`,
    `- 内容信号：${item.visualSignals.join("、") || item.visualSignal}`,
    `- 精细化状态：${item.precisionStatus?.text || "未填写"}`,
    `- 爆帖来源：${item.sourceTitle}`,
    `- 爆帖数据：赞${item.sourceMetrics.likes} / 评${item.sourceMetrics.comments} / 藏${item.sourceMetrics.favorites}`,
    `- 预览图：${item.contactSheet || "未生成"}`,
    "",
    "### 标题备选",
    "",
    ...item.titleOptions.map((title, titleIndex) => `${titleIndex + 1}. ${title}`),
    "",
    "### 正文",
    "",
    item.body,
    "",
    "### 标签",
    "",
    item.hashtags.map((tag) => `#${tag}`).join(" "),
    "",
    "### 图片文件",
    "",
    ...item.imageFiles.map((file, fileIndex) => `${fileIndex + 1}. ${file.kind}: ${file.path}`),
    "",
    "### 发布前检查",
    "",
    ...item.checks.map((check) => `- [ ] ${check}`),
    ""
  ])
].join("\n");

fs.writeFileSync(outputMdPath, markdown);
fs.writeFileSync(outputJsonPath, JSON.stringify({
  generatedAt: new Date().toISOString(),
  quality: manifest.quality,
  contactSheet: manifest.contactSheet,
  items: publishItems
}, null, 2));

console.log(`已生成 ${outputMdPath}`);
console.log(`已生成 ${outputJsonPath}`);
