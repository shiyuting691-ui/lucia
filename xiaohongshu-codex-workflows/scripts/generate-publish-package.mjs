import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const queuePath = path.join(root, "inputs", "publish-queue.json");
const outputPath = path.join(root, "outputs", "publish-ready.md");
const logPath = path.join(root, "outputs", "publish-queue-status.json");

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
    return item.body || `未找到正文来源：${item.bodySource}`;
  }

  const source = fs.readFileSync(sourcePath, "utf8");
  const marker = "## 正文草稿";
  const index = source.indexOf(marker);

  if (index === -1) {
    return source.trim();
  }

  return source
    .slice(index + marker.length)
    .split("\n## ")[0]
    .trim();
};

const pendingItems = queue.filter((item) => item.status !== "published");

const markdown = [
  "# 待发布包",
  "",
  "> 这个文件用于自动整理发布材料。最终发布到小红书前，需要人工确认。",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  "",
  "## 今日待处理",
  "",
  pendingItems.length
    ? `共有 ${pendingItems.length} 条待处理内容。`
    : "暂无待处理内容。",
  "",
  ...pendingItems.flatMap((item, index) => {
    const body = readBody(item);
    return [
      `## ${index + 1}. ${item.title || "未命名标题"}`,
      "",
      `- 内容ID：${item.id || "未填写"}`,
      `- 状态：${item.status || "pending_approval"}`,
      `- 账号：${item.accountName || "未填写"}`,
      `- 账号角色：${roleNames[item.accountRole] || item.accountRole || "未填写"}`,
      `- 搜索阶段：${funnelNames[item.searchFunnel] || item.searchFunnel || "未填写"}`,
      `- 计划发布时间：${item.scheduledAt || "未填写"}`,
      `- 封面思路：${item.coverIdea || "未填写"}`,
      `- 图片素材：${item.imageAssets?.length ? item.imageAssets.join("；") : "未填写"}`,
      `- 话题标签：${item.hashtags?.length ? item.hashtags.map((tag) => `#${tag}`).join(" ") : "未填写"}`,
      "",
      "### 正文",
      "",
      body || "未填写正文",
      "",
      "### 发布前检查",
      "",
      ...(item.prePublishChecks || []).map((check) => `- [ ] ${check}`),
      "- [ ] 人工确认标题、正文、图片、标签无误",
      "- [ ] 人工确认可以对外发布",
      "",
      "### 下一步",
      "",
      "人工确认后，再执行小红书客户端或网页版发布动作。",
      ""
    ];
  }),
  "## 合规边界",
  "",
  "- 本工作流只自动准备发布材料，不无人值守点击发布。",
  "- 不自动点赞、评论、关注、收藏或进行账号养号动作。",
  "- 不自动规避平台风控。"
].join("\n");

const status = {
  generatedAt: new Date().toISOString(),
  total: queue.length,
  pending: pendingItems.length,
  published: queue.filter((item) => item.status === "published").length,
  items: queue.map((item) => ({
    id: item.id,
    status: item.status,
    scheduledAt: item.scheduledAt,
    accountRole: item.accountRole,
    title: item.title
  }))
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, markdown);
fs.writeFileSync(logPath, JSON.stringify(status, null, 2));

console.log(`已生成 ${outputPath}`);
console.log(`已生成 ${logPath}`);
