/**
 * Unified configuration loader.
 *
 * Priority (highest wins):
 *   1. Environment variables (e.g. AGENT__MODEL=openai:gpt-4o)
 *   2. .env file
 *   3. .helius/settings.yaml
 *   4. Default values
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import dotenv from "dotenv";

function loadEnvOnce(): void {
  const candidates: string[] = [];
  candidates.push(path.resolve(process.cwd(), ".env"));
  try {
    const here = path.dirname(fileURLToPath(import.meta.url));
    candidates.push(path.resolve(here, "..", "..", ".env"));
  } catch {
    // ignore
  }

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      dotenv.config({ path: candidate });
      break;
    }
  }
}

// Load .env once. Existing process.env values still win.
loadEnvOnce();

// ── Types ───────────────────────────────────────────────────────────────────

type ReadonlyStringSet = ReadonlySet<string>;

export interface FilesystemConfig {
  max_file_size_mb: number;
  max_output_length: number;
  ignore_dirs: ReadonlyStringSet;
}

export interface ShellConfig {
  timeout_seconds: number;
  max_output_length: number;
  max_background_log_lines: number;
  allowlist: ReadonlyStringSet;
  dangerous: ReadonlyStringSet;
}

export interface GitConfig {
  safe_commands: ReadonlyStringSet;
  dangerous_commands: ReadonlyStringSet;
}

export interface SearchConfig {
  timeout_seconds: number;
  max_output_length: number;
}

export interface ToolsConfig {
  filesystem: FilesystemConfig;
  shell: ShellConfig;
  git: GitConfig;
  search: SearchConfig;
}

export interface AgentConfig {
  model: string;
  max_retries: number;
  retry_delay_seconds: number;
  thread_id_prefix: string;
}

export interface HITLConfig {
  interactive: boolean;
  default_action: "reject" | "approve";
}

export interface ObservabilityConfig {
  audit_file: string;
  log_level: string;
  log_format: "json" | "text";
}

export interface WorkspaceConfig {
  root: string | null;
}

export interface PromptsConfig {
  system_prompt_file: string;
}

export interface Settings {
  // Secrets
  google_api_key: string | null;
  openai_api_key: string | null;
  groq_api_key: string | null;
  hitl_bypass_token: string | null;

  // Structured sections
  agent: AgentConfig;
  tools: ToolsConfig;
  hitl: HITLConfig;
  observability: ObservabilityConfig;
  workspace: WorkspaceConfig;
  prompts: PromptsConfig;
}

// ── Defaults ────────────────────────────────────────────────────────────────

const DEFAULT_SETTINGS: Settings = {
  google_api_key: null,
  openai_api_key: null,
  groq_api_key: null,
  hitl_bypass_token: null,

  agent: {
    model: "google_genai:gemini-2.5-flash",
    max_retries: 3,
    retry_delay_seconds: 2.0,
    thread_id_prefix: "session",
  },

  tools: {
    filesystem: {
      max_file_size_mb: 5,
      max_output_length: 50_000,
      ignore_dirs: new Set([
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
      ]),
    },
    shell: {
      timeout_seconds: 120,
      max_output_length: 50_000,
      max_background_log_lines: 500,
      allowlist: new Set([
        "pwd", "ls", "dir", "echo", "cat", "type", "uname", "whoami", "hostname",
        "git", "python", "python3", "pip", "pytest", "uv",
        "node", "npm", "npx", "yarn", "tsc",
        "java", "javac", "go", "gcc", "g++", "rustc", "cargo",
        "make", "cmake", "docker",
        "grep", "find", "sort", "head", "tail", "clear", "cls",
      ]),
      dangerous: new Set(["rm", "del", "rmdir"]),
    },
    git: {
      safe_commands: new Set([
        "status", "log", "diff", "show", "branch", "checkout", "switch",
        "add", "commit", "stash", "pull", "fetch", "rev-parse",
      ]),
      dangerous_commands: new Set([
        "reset", "merge", "rebase", "clean", "restore", "revert", "rm",
      ]),
    },
    search: {
      timeout_seconds: 10,
      max_output_length: 50_000,
    },
  },

  hitl: {
    interactive: true,
    default_action: "reject",
  },

  observability: {
    audit_file: ".helius/agent_audit/audit.jsonl",
    log_level: "INFO",
    log_format: "json",
  },

  workspace: {
    root: null,
  },

  prompts: {
    system_prompt_file: ".helius/prompts/system_prompt.md",
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────

function toReadonlySet(value: unknown): ReadonlySet<string> {
  if (value instanceof Set) return value;
  if (Array.isArray(value)) return new Set(value.map(String));
  if (typeof value === "string" && value.trim()) {
    return new Set(value.split(",").map(s => s.trim()).filter(Boolean));
  }
  return new Set();
}

function toNumber(value: unknown, fallback: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function toBoolean(value: unknown, fallback: boolean): boolean {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "boolean") return value;
  const s = String(value).toLowerCase().trim();
  if (["1", "true", "yes", "y", "on"].includes(s)) return true;
  if (["0", "false", "no", "n", "off"].includes(s)) return false;
  return fallback;
}

function deepMerge<T>(base: T, patch: Partial<T>): T {
  if (patch === null || patch === undefined) return base;

  if (Array.isArray(base) || Array.isArray(patch)) {
    return (patch as T) ?? base;
  }

  if (typeof base !== "object" || typeof patch !== "object") {
    return (patch as T) ?? base;
  }

  const out: any = { ...(base as any) };
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) continue;
    const baseValue = (base as any)[key];
    out[key] =
      baseValue && value && typeof baseValue === "object" && typeof value === "object"
        ? deepMerge(baseValue, value as any)
        : value;
  }
  return out;
}

function loadYamlConfig(filePath = ".helius/settings.yaml"): Record<string, any> {
  if (!fs.existsSync(filePath)) {
    console.warn(`settings.yaml not found at '${filePath}'; using defaults.`);
    return {};
  }

  const raw = fs.readFileSync(filePath, "utf8");
  const parsed = parseYaml(raw);
  return (parsed && typeof parsed === "object") ? (parsed as Record<string, any>) : {};
}

function envToNestedConfig(env: NodeJS.ProcessEnv): Partial<Settings> {
  const out: any = {};

  // Secrets
  if (env.GOOGLE_API_KEY) out.google_api_key = env.GOOGLE_API_KEY;
  if (env.OPENAI_API_KEY) out.openai_api_key = env.OPENAI_API_KEY;
  if (env.GROQ_API_KEY) out.groq_api_key = env.GROQ_API_KEY;
  if (env.HITL_BYPASS_TOKEN) out.hitl_bypass_token = env.HITL_BYPASS_TOKEN;

  // Nested examples:
  // AGENT__MODEL=openai:gpt-4o
  // TOOLS__FILESYSTEM__MAX_FILE_SIZE_MB=10
  // WORKSPACE__ROOT=.
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) continue;

    const parts = key.toLowerCase().split("__");
    if (parts.length < 2) continue;

    let cursor: any = out;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      cursor[part] ??= {};
      cursor = cursor[part];
    }

    const leaf = parts[parts.length - 1];
    cursor[leaf] = value;
  }

  return out;
}

function normalizeSettings(raw: Partial<Settings>): Settings {
  const merged = deepMerge(DEFAULT_SETTINGS, raw);

  return {
    google_api_key: merged.google_api_key ?? null,
    openai_api_key: merged.openai_api_key ?? null,
    groq_api_key: merged.groq_api_key ?? null,
    hitl_bypass_token: merged.hitl_bypass_token ?? null,

    agent: {
      model: String(merged.agent?.model ?? DEFAULT_SETTINGS.agent.model),
      max_retries: toNumber(merged.agent?.max_retries, DEFAULT_SETTINGS.agent.max_retries),
      retry_delay_seconds: toNumber(
        merged.agent?.retry_delay_seconds,
        DEFAULT_SETTINGS.agent.retry_delay_seconds
      ),
      thread_id_prefix: String(
        merged.agent?.thread_id_prefix ?? DEFAULT_SETTINGS.agent.thread_id_prefix
      ),
    },

    tools: {
      filesystem: {
        max_file_size_mb: toNumber(
          merged.tools?.filesystem?.max_file_size_mb,
          DEFAULT_SETTINGS.tools.filesystem.max_file_size_mb
        ),
        max_output_length: toNumber(
          merged.tools?.filesystem?.max_output_length,
          DEFAULT_SETTINGS.tools.filesystem.max_output_length
        ),
        ignore_dirs: toReadonlySet(
          merged.tools?.filesystem?.ignore_dirs ?? DEFAULT_SETTINGS.tools.filesystem.ignore_dirs
        ),
      },
      shell: {
        timeout_seconds: toNumber(
          merged.tools?.shell?.timeout_seconds,
          DEFAULT_SETTINGS.tools.shell.timeout_seconds
        ),
        max_output_length: toNumber(
          merged.tools?.shell?.max_output_length,
          DEFAULT_SETTINGS.tools.shell.max_output_length
        ),
        max_background_log_lines: toNumber(
          merged.tools?.shell?.max_background_log_lines,
          DEFAULT_SETTINGS.tools.shell.max_background_log_lines
        ),
        allowlist: toReadonlySet(
          merged.tools?.shell?.allowlist ?? DEFAULT_SETTINGS.tools.shell.allowlist
        ),
        dangerous: toReadonlySet(
          merged.tools?.shell?.dangerous ?? DEFAULT_SETTINGS.tools.shell.dangerous
        ),
      },
      git: {
        safe_commands: toReadonlySet(
          merged.tools?.git?.safe_commands ?? DEFAULT_SETTINGS.tools.git.safe_commands
        ),
        dangerous_commands: toReadonlySet(
          merged.tools?.git?.dangerous_commands ?? DEFAULT_SETTINGS.tools.git.dangerous_commands
        ),
      },
      search: {
        timeout_seconds: toNumber(
          merged.tools?.search?.timeout_seconds,
          DEFAULT_SETTINGS.tools.search.timeout_seconds
        ),
        max_output_length: toNumber(
          merged.tools?.search?.max_output_length,
          DEFAULT_SETTINGS.tools.search.max_output_length
        ),
      },
    },

    hitl: {
      interactive: toBoolean(
        merged.hitl?.interactive,
        DEFAULT_SETTINGS.hitl.interactive
      ),
      default_action:
        merged.hitl?.default_action === "approve" ? "approve" : "reject",
    },

    observability: {
      audit_file: String(
        merged.observability?.audit_file ?? DEFAULT_SETTINGS.observability.audit_file
      ),
      log_level: String(
        merged.observability?.log_level ?? DEFAULT_SETTINGS.observability.log_level
      ),
      log_format:
        merged.observability?.log_format === "text" ? "text" : "json",
    },

    workspace: {
      root:
        merged.workspace?.root === undefined || merged.workspace?.root === null
          ? null
          : String(merged.workspace.root),
    },

    prompts: {
      system_prompt_file: String(
        merged.prompts?.system_prompt_file ?? DEFAULT_SETTINGS.prompts.system_prompt_file
      ),
    },
  };
}

// ── Singleton settings loader ───────────────────────────────────────────────

let cachedSettings: Settings | null = null;

export function getSettings(): Settings {
  if (cachedSettings) return cachedSettings;

  const yamlConfig = loadYamlConfig(".helius/settings.yaml");
  const envConfig = envToNestedConfig(process.env);

  // Precedence: defaults <- YAML <- .env/runtime env
  const merged = deepMerge(DEFAULT_SETTINGS, yamlConfig);
  const mergedWithEnv = deepMerge(merged, envConfig);

  cachedSettings = normalizeSettings(mergedWithEnv);
  return cachedSettings;
}

export function loadSystemPrompt(settings?: Settings): string {
  const cfg = settings ?? getSettings();
  const filePath = cfg.prompts.system_prompt_file;

  if (!fs.existsSync(filePath)) {
    console.warn(
      `System prompt file not found at '${filePath}'; using inline fallback.`
    );
    return "You are an expert AI software engineer. Use your tools to navigate, edit, and manage the repository.";
  }

  return fs.readFileSync(filePath, "utf8").trim();
}
