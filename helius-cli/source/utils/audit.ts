import fs from "node:fs";
import path from "node:path";
import { getSettings } from "./config.js";

interface AuditRecord {
  ts: string;
  thread_id: string;
  event: string;
  data?: any;
}

export function logAudit(threadId: string, event: string, data?: any) {
  const settings = getSettings();
  const auditPath = settings.observability.audit_file;
  const rootDir = settings.workspace.root ?? process.cwd();
  const fullPath = path.isAbsolute(auditPath) 
    ? auditPath 
    : path.resolve(rootDir, auditPath);

  const record: AuditRecord = {
    ts: new Date().toISOString(),
    thread_id: threadId,
    event,
    data,
  };

  try {
    fs.mkdirSync(path.dirname(fullPath), { recursive: true });
    fs.appendFileSync(fullPath, JSON.stringify(record) + "\n", "utf8");
  } catch (err) {
    // Fail silently to not disrupt the agent
    console.error("Failed to write to audit log:", err);
  }
}
