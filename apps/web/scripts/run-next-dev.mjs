import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SUPPORTED_MAJORS = new Set([20, 22]);
const CURRENT_MAJOR = Number.parseInt(process.versions.node.split(".")[0] ?? "", 10);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appRoot = path.resolve(__dirname, "..");
const nextBin = path.join(appRoot, "node_modules", "next", "dist", "bin", "next");
const fallbackNodes = ["/opt/homebrew/opt/node@22/bin/node", "/opt/homebrew/opt/node@20/bin/node"];

let selectedNode = process.execPath;
if (!SUPPORTED_MAJORS.has(CURRENT_MAJOR)) {
  selectedNode = fallbackNodes.find((candidate) => existsSync(candidate)) ?? "";
  if (!selectedNode) {
    console.error(
      [
        `[utah-subdivision] Unsupported Node runtime for \`npm run dev\`: ${process.version}.`,
        "Install Homebrew node@22 or node@20, or switch your shell to a supported runtime.",
        "This repo pins the expected version in .nvmrc and package.json.",
      ].join("\n")
    );
    process.exit(1);
  }
  console.error(`[utah-subdivision] Using fallback runtime ${selectedNode} for Next dev.`);
}

if (!existsSync(nextBin)) {
  console.error(`[utah-subdivision] Next.js binary not found at ${nextBin}. Run npm install in apps/web first.`);
  process.exit(1);
}

const child = spawn(selectedNode, [nextBin, "dev", ...process.argv.slice(2)], {
  cwd: appRoot,
  env: process.env,
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
