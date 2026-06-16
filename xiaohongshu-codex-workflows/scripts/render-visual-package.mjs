import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const bundledPython = "/Users/meilucia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const pythonBin = fs.existsSync(bundledPython) ? bundledPython : "python3";
const scriptPath = path.join(root, "scripts", "render-visual-package.py");

const result = spawnSync(pythonBin, [scriptPath], {
  cwd: root,
  stdio: "inherit"
});

if (result.status !== 0) {
  process.exit(result.status || 1);
}
