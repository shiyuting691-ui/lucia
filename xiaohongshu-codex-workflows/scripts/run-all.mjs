import { spawn } from "node:child_process";
import path from "node:path";

const root = path.resolve(process.cwd());

const tasks = [
  ["collect", "node", ["scripts/collect-xhs-keywords.mjs"]],
  ["collect:source", "node", ["scripts/collect-xhs-source.mjs"]],
  ["collect:import", "node", ["scripts/import-hotposts-text.mjs"]],
  ["collect:api", "node", ["scripts/collect-xhs-api.mjs"]],
  ["collect:apify", "node", ["scripts/collect-xhs-apify.mjs"]],
  ["analyze", "node", ["scripts/analyze-hotposts.mjs"]],
  ["draft", "node", ["scripts/generate-post-draft.mjs"]],
  ["ops", "node", ["scripts/generate-ops-checklist.mjs"]],
  ["publish", "node", ["scripts/generate-publish-package.mjs"]],
  ["wechat", "node", ["scripts/generate-wechat-digest.mjs"]],
  ["push:wechat", "node", ["scripts/send-wechat-webhook.mjs"]]
];

const runTask = ([name, command, args]) =>
  new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      stdio: "inherit"
    });

    child.on("close", (code) => {
      if (code === 0) {
        resolve();
        return;
      }

      reject(new Error(`${name} failed with exit code ${code}`));
    });
  });

console.log("开始自动跑完整工作流...");

for (const task of tasks) {
  console.log(`\n--- ${task[0]} ---`);
  await runTask(task);
}

console.log("\n全部完成。输出文件已更新到 outputs/。");
