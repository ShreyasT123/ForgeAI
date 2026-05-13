import { tool } from "langchain";
import { z } from "zod";
import fs from "node:fs";
import path from "node:path";
import { getSettings } from "../utils/config.js";
import { getLogger } from "../utils/logger.js";
import { resolveWorkspacePath, truncate } from "../utils/security.js";

const logger = getLogger("tools.intelligence");

function workspaceRoot(): string {
  const root = getSettings().workspace.root;
  return path.resolve(root ?? process.cwd());
}

// Regex patterns for symbols in various languages
const SYMBOL_PATTERNS: Record<string, RegExp> = {
  typescript: /(?:export\s+)?(?:class|interface|type|enum|function|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)/g,
  javascript: /(?:export\s+)?(?:class|function|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)/g,
  python: /(?:class|def)\s+([a-zA-Z_][a-zA-Z0-9_]*)/g,
  go: /(?:type|func|const|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)/g,
  rust: /(?:pub\s+)?(?:struct|enum|trait|type|fn|const|static)\s+([a-zA-Z_][a-zA-Z0-9_]*)/g,
};

const searchSymbolsTool = tool(
  async ({ query, path: targetPath = "." }: { query: string; path?: string }) => {
    try {
      logger.info(`search_symbols query=${query} path=${targetPath}`);
      const ws = workspaceRoot();
      const target = resolveWorkspacePath(targetPath, ws);
      
      const results: string[] = [];
      const regex = new RegExp(query, "i");

      const scanFile = (fp: string) => {
        const ext = path.extname(fp).slice(1);
        let lang = "javascript";
        if (["ts", "tsx"].includes(ext)) lang = "typescript";
        else if (ext === "py") lang = "python";
        else if (ext === "go") lang = "go";
        else if (ext === "rs") lang = "rust";
        
        const pattern = SYMBOL_PATTERNS[lang] || SYMBOL_PATTERNS.javascript;
        const content = fs.readFileSync(fp, "utf8");
        const lines = content.split("\n");
        
        pattern.lastIndex = 0;
        let match;
        while ((match = pattern.exec(content)) !== null) {
          const symbolName = match[1];
          if (regex.test(symbolName)) {
            const index = match.index;
            const lineNum = content.slice(0, index).split("\n").length;
            const rel = path.relative(ws, fp);
            results.push(`${rel}:${lineNum}: [${lang}] ${match[0].trim()}`);
          }
        }
      };

      const walk = (dir: string) => {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.name.startsWith(".") || entry.name === "node_modules" || entry.name === "dist") continue;
          const full = path.join(dir, entry.name);
          if (entry.isDirectory()) walk(full);
          else if (entry.isFile()) scanFile(full);
        }
      };

      if (fs.statSync(target).isFile()) scanFile(target);
      else walk(target);

      return truncate(results.join("\n") || "No matching symbols found.", 50000);
    } catch (err) {
      logger.error("search_symbols error", err);
      return `Error: ${(err as Error).message}`;
    }
  },
  {
    name: "search_symbols",
    description: "Search for classes, functions, or variables across the codebase using regex matching on symbol names.",
    schema: z.object({
      query: z.string().describe("The symbol name or pattern to search for."),
      path: z.string().optional().describe("Directory or file to search within."),
    }),
  }
);

export const INTELLIGENCE_TOOLS = [searchSymbolsTool];
