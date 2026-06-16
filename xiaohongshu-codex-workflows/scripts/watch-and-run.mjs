import fs from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";

const root = path.resolve(process.cwd());
const watchFiles = [
  "inputs/hotposts.json",
  "inputs/collect-keywords.json",
  "inputs/post-brief.json",
  "inputs/publish-queue.json",
  "knowledge/sop-rules.json",
  "templates/analysis-template.md",
  "templates/post-template.md",
  "templates/student-post-template.md",
  "templates/ip-post-template.md",
  "templates/business-post-template.md"
].map((file) => path.join(root, file));
let running = false;
let pending = false;
let timer = null;

const runAll = () =>
  new Promise((resolve) => {
    running = true;
    const startedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    console.log(`\n[${startedAt}] 检测到变化，开始自动生成...`);

    const child = spawn("node", ["scripts/run-all.mjs"], {
      cwd: root,
      stdio: "inherit"
    });

    child.on("close", () => {
      running = false;
      resolve();

      if (pending) {
        pending = false;
        scheduleRun();
      }
    });
  });

const scheduleRun = () => {
  if (running) {
    pending = true;
    return;
  }

  clearTimeout(timer);
  timer = setTimeout(() => {
    runAll();
  }, 500);
};

for (const file of watchFiles) {
  fs.watchFile(file, { interval: 1000 }, (current, previous) => {
    if (current.mtimeMs !== previous.mtimeMs) {
      scheduleRun();
    }
  });
}

console.log("自动监听已启动。修改关键输入、规则或模版文件后会自动重跑。");
console.log("按 Ctrl+C 可以停止。");

await runAll();
