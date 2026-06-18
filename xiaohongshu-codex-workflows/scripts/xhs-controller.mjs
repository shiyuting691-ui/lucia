import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { loadEnvFile } from "./load-env.mjs";

const root = path.resolve(process.cwd());
loadEnvFile(root);

const workflowStartedAt = Date.now();
const runDate = new Date().toISOString().slice(0, 10);
const runTimestamp = new Date().toISOString().replace(/[:.]/g, "-");
const runId = process.env.XHS_RUN_ID || `${runDate}-${runTimestamp}`;

const legacyOutputsDir = path.join(root, "outputs");
const runOutputsDir = path.join(root, "outputs", "runs", runId);
const latestOutputsDir = path.join(root, "outputs", "latest");
const statusJsonPath = path.join(legacyOutputsDir, "controller-status.json");
const statusMdPath = path.join(legacyOutputsDir, "controller-status.md");

const args = process.argv.slice(2);
const modeArg = args.find((arg) => arg.startsWith("--mode="));
const mode = modeArg ? modeArg.split("=")[1] : "daily";
const workflowConfigPath = path.join(root, "configs", "workflows", `${mode}.json`);

const stepDefinitions = {
  "config:check": { group: "config", label: "配置检查", required: false },
  collect: { group: "collect", label: "关键词采集计划", required: true },
  "collect:source": { group: "collect", label: "外部数据源导入", required: false },
  "collect:lark": { group: "collect", label: "飞书表格采集", required: false },
  "collect:social": { group: "collect", label: "社媒助手表格采集", required: false },
  "collect:inbox": { group: "collect", label: "自动收集 Inbox", required: false },
  "collect:import": { group: "collect", label: "文本热帖导入", required: false },
  "collect:api": { group: "collect", label: "公开接口探测", required: false },
  "collect:apify": { group: "collect", label: "Apify 采集", required: false },
  analyze: { group: "analysis", label: "热帖分析", required: true },
  draft: { group: "production", label: "文案草稿", required: true },
  "draft:roles": { group: "production", label: "三账号 SOP 草稿", required: true },
  "draft:courses": { group: "production", label: "课程作业精细化草稿", required: true },
  "visual:render": { group: "production", label: "PNG 图片渲染", required: true },
  ops: { group: "production", label: "运营清单", required: true },
  "publish:roles": { group: "production", label: "三账号发布包", required: true },
  publish: { group: "production", label: "待发布包", required: true },
  wechat: { group: "delivery", label: "微信日报", required: true },
  "push:wechat": { group: "delivery", label: "企业微信推送", required: true },
  "push:wxpusher": {
    group: "delivery",
    label: "WxPusher 推送",
    required: false,
    when: () => process.env.XHS_AUTO_PUSH_WXPUSHER === "true",
    skipReason: "XHS_AUTO_PUSH_WXPUSHER 未设置为 true"
  },
  "push:lark": {
    group: "delivery",
    label: "飞书推送",
    required: false,
    when: () => process.env.XHS_AUTO_PUSH_LARK === "true",
    skipReason: "XHS_AUTO_PUSH_LARK 未设置为 true"
  }
};

const fallbackWorkflowConfig = {
  name: "兼容完整流程",
  description: "未找到配置文件时使用的旧版完整流程",
  steps: [
    "config:check",
    "collect",
    "collect:source",
    "collect:lark",
    "collect:social",
    "collect:inbox",
    "collect:import",
    "collect:api",
    "collect:apify",
    "analyze",
    "draft",
    "draft:roles",
    "draft:courses",
    "visual:render",
    "ops",
    "publish:roles",
    "publish",
    "wechat",
    "push:wechat",
    "push:wxpusher",
    "push:lark"
  ],
  expectedOutputs: [
    "outputs/collection-plan.md",
    "outputs/hotpost-analysis.md",
    "outputs/post-draft.md",
    "outputs/role-based-post-drafts.md",
    "outputs/course-precision-post-drafts.md",
    "outputs/visual-package.md",
    "outputs/visual-images/manifest.json",
    "outputs/role-publish-ready.md",
    "outputs/account-ops-checklist.md",
    "outputs/publish-ready.md",
    "outputs/wechat-daily-digest.txt"
  ]
};

const readWorkflowConfig = () => {
  if (!fs.existsSync(workflowConfigPath)) {
    console.warn(`未找到 workflow 配置：configs/workflows/${mode}.json`);
    console.warn("使用旧版完整流程 fallback。");
    return { config: fallbackWorkflowConfig, found: false };
  }

  return {
    config: JSON.parse(fs.readFileSync(workflowConfigPath, "utf8")),
    found: true
  };
};

const { config: workflowConfig, found: workflowConfigFound } = readWorkflowConfig();

const buildWorkflow = (config) =>
  config.steps.map((scriptName) => {
    const definition = stepDefinitions[scriptName];
    if (!definition) {
      throw new Error(`workflow 配置包含未知步骤：${scriptName}`);
    }

    return {
      ...definition,
      scriptName,
      command: "npm",
      args: ["run", scriptName]
    };
  });

const workflow = buildWorkflow(workflowConfig);
const expectedOutputs = workflowConfig.expectedOutputs || fallbackWorkflowConfig.expectedOutputs;

const runStep = (step) =>
  new Promise((resolve) => {
    const startedAt = Date.now();
    const child = spawn(step.command, step.args, {
      cwd: root,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        XHS_RUN_ID: runId,
        XHS_OUTPUT_DIR: legacyOutputsDir,
        XHS_RUN_OUTPUT_DIR: runOutputsDir,
        XHS_LATEST_OUTPUT_DIR: latestOutputsDir
      }
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      stdout += text;
      process.stdout.write(text);
    });

    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      process.stderr.write(text);
    });

    child.on("close", (code) => {
      resolve({
        ...step,
        code,
        ok: code === 0,
        durationMs: Date.now() - startedAt,
        stdout: stdout.trim().slice(-2000),
        stderr: stderr.trim().slice(-2000)
      });
    });
  });

const outputExists = (relativePath) => fs.existsSync(path.join(root, relativePath));

const outputFresh = (relativePath) => {
  const fullPath = path.join(root, relativePath);
  if (!fs.existsSync(fullPath)) return false;
  const stat = fs.statSync(fullPath);
  return stat.mtimeMs >= workflowStartedAt;
};

const removeIfExists = (target) => {
  if (fs.existsSync(target)) {
    fs.rmSync(target, { recursive: true, force: true });
  }
};

const copyFileToOutputDirs = (relativePath) => {
  const source = path.join(root, relativePath);
  const outputRelativePath = path.relative(legacyOutputsDir, source);
  const destinations = [
    path.join(runOutputsDir, outputRelativePath),
    path.join(latestOutputsDir, outputRelativePath)
  ];

  for (const destination of destinations) {
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(source, destination);
  }
};

const directoryFresh = (directoryPath) => {
  if (!fs.existsSync(directoryPath)) return false;
  const entries = fs.readdirSync(directoryPath, { withFileTypes: true });
  return entries.some((entry) => {
    const fullPath = path.join(directoryPath, entry.name);
    if (entry.isDirectory()) return directoryFresh(fullPath);
    return fs.statSync(fullPath).mtimeMs >= workflowStartedAt;
  });
};

const copyDirectoryToOutputDirs = (relativePath) => {
  const source = path.join(root, relativePath);
  const outputRelativePath = path.relative(legacyOutputsDir, source);
  const destinations = [
    path.join(runOutputsDir, outputRelativePath),
    path.join(latestOutputsDir, outputRelativePath)
  ];

  for (const destination of destinations) {
    removeIfExists(destination);
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.cpSync(source, destination, { recursive: true });
  }
};

const archiveFreshOutputs = () => {
  removeIfExists(runOutputsDir);
  removeIfExists(latestOutputsDir);

  const files = expectedOutputs.map((file) => {
    const exists = outputExists(file);
    const fresh = exists && outputFresh(file);
    if (fresh) copyFileToOutputDirs(file);
    return { file, exists, fresh, copied: fresh };
  });

  const visualImagesRelative = "outputs/visual-images";
  const visualImagesPath = path.join(root, visualImagesRelative);
  const visualImages = {
    path: visualImagesRelative,
    exists: fs.existsSync(visualImagesPath),
    fresh: directoryFresh(visualImagesPath),
    copied: false
  };

  if (visualImages.exists && visualImages.fresh) {
    copyDirectoryToOutputDirs(visualImagesRelative);
    visualImages.copied = true;
  }

  return { files, visualImages };
};

console.log("启动小红书总控工作流...");
console.log(`模式：${mode}`);
console.log(`Run ID：${runId}`);

const results = [];
let aborted = false;

for (const step of workflow) {
  if (step.when && !step.when()) {
    const result = {
      ...step,
      code: 0,
      ok: true,
      skipped: true,
      durationMs: 0,
      stdout: step.skipReason || "已跳过",
      stderr: ""
    };
    results.push(result);
    console.log(`\n=== ${step.group}: ${step.label} ===`);
    console.log(`已跳过：${result.stdout}`);
    continue;
  }

  console.log(`\n=== ${step.group}: ${step.label} ===`);
  const result = await runStep(step);
  results.push(result);

  if (!result.ok && step.required) {
    console.error(`关键步骤失败，停止总控工作流：${step.label}`);
    aborted = true;
    break;
  }
}

const missingOutputs = expectedOutputs.filter((file) => !outputFresh(file));
const failedRequired = results.filter((item) => item.required && !item.ok);
const failedOptional = results.filter((item) => !item.required && !item.ok);
const archive = archiveFreshOutputs();
const ok = !aborted && failedRequired.length === 0 && missingOutputs.length === 0;

const status = {
  runId,
  mode,
  runOutputsDir,
  latestOutputsDir,
  workflowConfigPath,
  workflowConfigFound,
  workflowName: workflowConfig.name || mode,
  generatedAt: new Date().toISOString(),
  ok,
  aborted,
  failedRequired: failedRequired.map((item) => item.label),
  failedOptional: failedOptional.map((item) => item.label),
  missingOutputs,
  archive,
  results: results.map(({ stdout, stderr, ...item }) => ({
    ...item,
    stdoutTail: stdout,
    stderrTail: stderr
  }))
};

const grouped = results.reduce((acc, item) => {
  acc[item.group] ||= [];
  acc[item.group].push(item);
  return acc;
}, {});

const stepStatus = (item) => {
  if (item.skipped) return "SKIP";
  if (item.ok) return "OK";
  return item.required ? "FAIL" : "OPTIONAL_FAIL";
};

const markdown = [
  "# 小红书总控工作流状态",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `当前模式：${mode}`,
  `Run ID：${runId}`,
  `最新结果目录：${latestOutputsDir}`,
  `历史归档目录：${runOutputsDir}`,
  `Workflow 配置：${workflowConfigFound ? workflowConfigPath : `未找到，fallback：${workflowConfigPath}`}`,
  `整体状态：${ok ? "成功" : "需处理"}`,
  `是否中断：${aborted ? "是" : "否"}`,
  "",
  "## 分组状态",
  "",
  ...Object.entries(grouped).flatMap(([group, items]) => [
    `### ${group}`,
    "",
    ...items.map((item) => `- ${stepStatus(item)} ${item.label} (${item.durationMs}ms)`),
    ""
  ]),
  "## 关键输出",
  "",
  ...expectedOutputs.map((file) => `- ${outputFresh(file) ? "FRESH" : "MISSING_OR_STALE"} ${file}`),
  "",
  "## 归档结果",
  "",
  ...archive.files.map((item) => `- ${item.copied ? "COPIED" : "SKIP"} ${item.file}`),
  `- ${archive.visualImages.copied ? "COPIED" : "SKIP"} ${archive.visualImages.path}`,
  "",
  "## 待处理",
  "",
  `- missingOutputs：${missingOutputs.length ? missingOutputs.join("、") : "无"}`,
  `- failedRequired：${failedRequired.length ? failedRequired.map((item) => item.label).join("、") : "无"}`,
  `- failedOptional：${failedOptional.length ? failedOptional.map((item) => item.label).join("、") : "无"}`,
  ...(failedRequired.length ? failedRequired.map((item) => `- 关键失败：${item.label}`) : []),
  ...(failedOptional.length ? failedOptional.map((item) => `- 可选失败/跳过：${item.label}`) : []),
  ...(missingOutputs.length ? missingOutputs.map((file) => `- 缺少或非本次生成：${file}`) : []),
  !failedRequired.length && !failedOptional.length && !missingOutputs.length ? "- 无" : ""
].join("\n");

fs.mkdirSync(legacyOutputsDir, { recursive: true });
fs.writeFileSync(statusJsonPath, JSON.stringify(status, null, 2));
fs.writeFileSync(statusMdPath, markdown);

copyFileToOutputDirs("outputs/controller-status.json");
copyFileToOutputDirs("outputs/controller-status.md");

console.log(`\n已生成 ${statusJsonPath}`);
console.log(`已生成 ${statusMdPath}`);
console.log(`已归档到 ${runOutputsDir}`);
console.log(`已更新最新结果目录 ${latestOutputsDir}`);
console.log(ok ? "总控工作流完成。" : "总控工作流完成，但存在可处理事项。");

if (failedRequired.length || missingOutputs.length) {
  process.exitCode = 1;
}
