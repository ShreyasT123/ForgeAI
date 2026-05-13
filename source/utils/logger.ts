// logger.ts

/**
 * Centralized logging configuration.
 * Call configureLogging() exactly once at startup.
 */

import fs from "node:fs";
import path from "node:path";

type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR";
type LogFormat = "json" | "text";

interface LogRecord {
  ts: number;
  level: string;
  logger: string;
  msg: string;
  exc?: string;
  stack?: string;
}

let currentLevel: LogLevel = "INFO";
let currentFormat: LogFormat = "json";
let logStream: fs.WriteStream | null = null;

function ensureLogStream(): fs.WriteStream | null {
  if (logStream) return logStream;
  try {
    const baseDir = path.resolve(process.cwd(), ".helius", "logs");
    fs.mkdirSync(baseDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const filePath = path.join(baseDir, `debug-${stamp}.log`);
    logStream = fs.createWriteStream(filePath, { flags: "a" });
    return logStream;
  } catch {
    return null;
  }
}

// Priority map (like Python logging)
const LEVEL_PRIORITY: Record<LogLevel, number> = {
  DEBUG: 10,
  INFO: 20,
  WARNING: 30,
  ERROR: 40,
};

// ── Internal Logger Class ───────────────────────────────────────────────────

class Logger {
  constructor(private name: string) {}

  private shouldLog(level: LogLevel): boolean {
    return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[currentLevel];
  }

  private emit(level: LogLevel, msg: string, err?: unknown) {
    if (!this.shouldLog(level)) return;

    const record: LogRecord = {
      ts: Date.now() / 1000,
      level,
      logger: this.name,
      msg,
    };

    if (err instanceof Error) {
      record.exc = err.message;
      record.stack = err.stack;
    }

    const line =
      currentFormat === "json"
        ? JSON.stringify(record)
        : `[${level}] [${this.name}] ${msg}`;

    const stream = ensureLogStream();
    if (stream) {
      stream.write(line + "\n");
    }
  }

  debug(msg: string) {
    this.emit("DEBUG", msg);
  }

  info(msg: string) {
    this.emit("INFO", msg);
  }

  warn(msg: string) {
    this.emit("WARNING", msg);
  }

  error(msg: string, err?: unknown) {
    this.emit("ERROR", msg, err);
  }
}

// ── Public API ──────────────────────────────────────────────────────────────

function normalizeLevel(level: string): LogLevel {
  const upper = level.toUpperCase();
  if (upper === "DEBUG" || upper === "INFO" || upper === "WARNING" || upper === "ERROR") {
    return upper as LogLevel;
  }
  return "INFO";
}

function normalizeFormat(fmt: string): LogFormat {
  return fmt === "text" ? "text" : "json";
}

export function configureLogging(
  level: LogLevel | string = "INFO",
  fmt: LogFormat | string = "json"
) {
  currentLevel = normalizeLevel(String(level));
  currentFormat = normalizeFormat(String(fmt));

  // Silence noisy libraries (you'll manually control them if needed)
  // In Node/Bun, this is conceptual — you control logs via your wrappers
}

// Factory (like logging.getLogger)
const loggerCache = new Map<string, Logger>();

export function getLogger(name: string): Logger {
  if (!loggerCache.has(name)) {
    loggerCache.set(name, new Logger(name));
  }
  return loggerCache.get(name)!;
}
