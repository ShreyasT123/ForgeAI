import fs from "node:fs";
import path from "node:path";
import os from "node:os";

export type SessionInfo = {
  thread_id: string;
  checkpoint_count: number;
  latest_ts: string | null;
  latest_id: string | null;
  thread_dir: string;
  preview: string;
};

function readJson(filePath: string): Record<string, unknown> | null {
  try {
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function extractPreview(checkpoint: Record<string, unknown>): string {
  try {
    const channelValues = (checkpoint.channel_values ?? {}) as Record<string, unknown>;
    const messagesBlob = channelValues.messages;
    if (typeof messagesBlob === "string") return messagesBlob.slice(0, 80);
    return "";
  } catch {
    return "";
  }
}

function listCheckpointFiles(threadDir: string): string[] {
  const checkpointsDir = path.join(threadDir, "checkpoints");
  if (!fs.existsSync(checkpointsDir)) return [];

  const results: string[] = [];
  const stack = [checkpointsDir];
  while (stack.length > 0) {
    const current = stack.pop() as string;
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else if (entry.isFile() && entry.name.endsWith(".json")) {
        results.push(full);
      }
    }
  }
  return results.sort();
}

export class SessionStore {
  base_dir: string;

  constructor(baseDir?: string) {
    this.base_dir = baseDir ?? path.join(os.homedir(), ".helius", "sessions");
  }

  *list(): Iterable<SessionInfo> {
    if (!fs.existsSync(this.base_dir)) return;

    const infos: SessionInfo[] = [];
    const threadDirs = fs.readdirSync(this.base_dir, { withFileTypes: true });
    for (const entry of threadDirs) {
      if (!entry.isDirectory()) continue;
      const threadDir = path.join(this.base_dir, entry.name);
      const checkpoints = listCheckpointFiles(threadDir);
      if (checkpoints.length === 0) continue;

      const latestData = readJson(checkpoints[checkpoints.length - 1]) ?? {};
      const cp = (latestData.checkpoint ?? {}) as Record<string, unknown>;
      const latest_ts = (cp.ts as string) ?? null;
      const latest_id = (cp.id as string) ?? null;
      const preview = extractPreview(cp);

      infos.push({
        thread_id: entry.name,
        checkpoint_count: checkpoints.length,
        latest_ts,
        latest_id,
        thread_dir: threadDir,
        preview,
      });
    }

    infos.sort((a, b) => String(b.latest_ts ?? "").localeCompare(String(a.latest_ts ?? "")));
    for (const info of infos) {
      yield info;
    }
  }

  resumeConfig(threadId: string): Record<string, unknown> {
    return { configurable: { thread_id: threadId } };
  }

  latestConfig(): Record<string, unknown> | null {
    for (const info of this.list()) {
      return this.resumeConfig(info.thread_id);
    }
    return null;
  }

  get(threadId: string): SessionInfo | null {
    for (const info of this.list()) {
      if (info.thread_id === threadId) return info;
    }
    return null;
  }

  delete(threadId: string): boolean {
    const td = path.join(this.base_dir, threadId);
    if (fs.existsSync(td)) {
      fs.rmSync(td, { recursive: true, force: true });
      return true;
    }
    return false;
  }

  deleteAll(): number {
    let count = 0;
    if (!fs.existsSync(this.base_dir)) return 0;
    const entries = fs.readdirSync(this.base_dir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      fs.rmSync(path.join(this.base_dir, entry.name), { recursive: true, force: true });
      count += 1;
    }
    return count;
  }

  printList(): void {
    const sessions = Array.from(this.list());
    if (sessions.length === 0) {
      console.log("No sessions found.");
      return;
    }
    console.log(
      `${"#".padEnd(4)} ${"Thread ID".padEnd(36)} ${"Last active".padEnd(
        20
      )} ${"Cps".padStart(4)}  Preview`
    );
    console.log("-".repeat(100));
    sessions.forEach((s, idx) => {
      const ts = String(s.latest_ts ?? "").slice(0, 19).replace("T", " ");
      const preview = s.preview.slice(0, 50);
      console.log(
        `${String(idx + 1).padEnd(4)} ${s.thread_id.padEnd(36)} ${ts.padEnd(
          20
        )} ${String(s.checkpoint_count).padStart(4)}  ${preview}`
      );
    });
  }
}
