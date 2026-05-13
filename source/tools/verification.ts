import { spawnSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { tool } from "langchain";
import { z } from "zod";
import { getSettings } from "../utils/config.js";
import { getLogger } from "../utils/logger.js";
import { truncate } from "../utils/security.js";

const logger = getLogger("tools.verification");

function workspaceRoot(): string {
  const root = getSettings().workspace.root;
  return path.resolve(root ?? process.cwd());
}

const verifyTool = tool(
  async ({ command, type }: { command?: string; type?: "lint" | "test" | "build" | "custom" }) => {
    const ws = workspaceRoot();
    logger.info(`verify cmd=${command} type=${type}`);

    let execCmd = command;
    if (!execCmd) {
      if (type === "lint") {
        if (fs.existsSync(path.join(ws, "package.json"))) execCmd = "npm run lint";
        else if (fs.existsSync(path.join(ws, "pyproject.toml"))) execCmd = "ruff check .";
      } else if (type === "test") {
        if (fs.existsSync(path.join(ws, "package.json"))) execCmd = "npm test";
        else if (fs.existsSync(path.join(ws, "pyproject.toml"))) execCmd = "pytest";
      } else if (type === "build") {
        if (fs.existsSync(path.join(ws, "package.json"))) execCmd = "npm run build";
      }
    }

    if (!execCmd) return "Error: No command provided and could not auto-detect for type.";

    const [cmd, ...args] = execCmd.split(" ");
    try {
      const result = spawnSync(cmd, args, {
        cwd: ws,
        encoding: "utf8",
        shell: true,
      });

      const output = `Exit Code: ${result.status}\nSTDOUT:\n${result.stdout}\nSTDERR:\n${result.stderr}`;
      if (result.status === 0) {
        return `Verification PASSED:\n${truncate(output, 5000)}`;
      }
      return `Verification FAILED:\n${truncate(output, 10000)}`;
    } catch (err) {
      return `Execution error: ${(err as Error).message}`;
    }
  },
  {
    name: "verify",
    description: "Run verification commands (lint, test, build) to ensure code quality. Proactively use this after making changes.",
    schema: z.object({
      command: z.string().optional().describe("Specific command to run (e.g. 'npm run lint')."),
      type: z.enum(["lint", "test", "build", "custom"]).optional().describe("Type of verification."),
    }),
  }
);

export const VERIFICATION_TOOLS = [verifyTool];
