import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

import {
  BaseCheckpointSaver,
  Checkpoint,
  CheckpointMetadata,
  CheckpointTuple,
  getCheckpointId,
} from "@langchain/langgraph-checkpoint";
import type { CheckpointListOptions, PendingWrite } from "@langchain/langgraph-checkpoint";
import type { RunnableConfig } from "@langchain/core/runnables";

const NS_ROOT = "__root__";

function expandHome(p: string): string {
  if (p.startsWith("~" + path.sep) || p === "~") {
    return path.join(os.homedir(), p.slice(1));
  }
  return p;
}

function nsDir(ns: string): string {
  return ns === "" ? NS_ROOT : ns;
}

type EncodedValue = {
  __type__: string;
  __data__: unknown;
  __bytes__: boolean;
};

export class JsonFileSaver extends BaseCheckpointSaver<number> {
  baseDir: string;

  constructor(baseDir?: string) {
    super();
    this.baseDir = baseDir
      ? expandHome(baseDir)
      : path.join(os.homedir(), ".helius", "sessions");
  }

  private threadDir(threadId: string): string {
    return path.join(this.baseDir, threadId);
  }

  private checkpointDir(threadId: string, ns: string): string {
    return path.join(this.threadDir(threadId), "checkpoints", nsDir(ns));
  }

  private checkpointPath(threadId: string, ns: string, checkpointId: string): string {
    return path.join(this.checkpointDir(threadId, ns), `${checkpointId}.json`);
  }

  private writesDir(threadId: string, checkpointId: string): string {
    return path.join(this.threadDir(threadId), "writes", checkpointId);
  }

  private async encodeValue(value: unknown): Promise<EncodedValue> {
    const [typeTag, data] = await this.serde.dumpsTyped(value);
    if (data instanceof Uint8Array) {
      return {
        __type__: typeTag,
        __data__: Buffer.from(data).toString("base64"),
        __bytes__: true,
      };
    }
    return { __type__: typeTag, __data__: data, __bytes__: false };
  }

  private async decodeValue(blob: unknown): Promise<unknown> {
    if (!blob || typeof blob !== "object") return blob;
    const rec = blob as EncodedValue;
    if (!("__type__" in rec)) return blob;
    let data = rec.__data__;
    if (rec.__bytes__) {
      if (typeof data !== "string") return null;
      data = Buffer.from(data, "base64");
    }
    return await this.serde.loadsTyped(rec.__type__, data as Uint8Array | string);
  }

  private async encodeChannelValues(
    channelValues: Record<string, unknown>
  ): Promise<Record<string, EncodedValue>> {
    const out: Record<string, EncodedValue> = {};
    for (const [key, value] of Object.entries(channelValues)) {
      out[key] = await this.encodeValue(value);
    }
    return out;
  }

  private async decodeChannelValues(
    raw: Record<string, EncodedValue>
  ): Promise<Record<string, unknown>> {
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(raw)) {
      out[key] = await this.decodeValue(value);
    }
    return out;
  }

  private async packCheckpoint(checkpoint: Checkpoint): Promise<Record<string, unknown>> {
    const packed = { ...checkpoint };
    packed.channel_values = await this.encodeChannelValues(
      checkpoint.channel_values ?? {}
    );
    return packed;
  }

  private async unpackCheckpoint(raw: Record<string, unknown>): Promise<Checkpoint> {
    const unpacked: Record<string, unknown> = { ...raw };
    const values = (raw.channel_values ?? {}) as Record<string, EncodedValue>;
    unpacked.channel_values = await this.decodeChannelValues(values);
    return unpacked as unknown as Checkpoint;
  }

  private async writeJson(filePath: string, data: Record<string, unknown>): Promise<void> {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    const tmp = `${filePath}.tmp`;
    try {
      await fs.writeFile(tmp, JSON.stringify(data, null, 2), "utf8");
      await fs.rename(tmp, filePath);
    } catch (err) {
      try {
        await fs.unlink(tmp);
      } catch {
        // ignore
      }
      throw err;
    }
  }

  private async readJson(
    filePath: string
  ): Promise<Record<string, unknown> | null> {
    try {
      const raw = await fs.readFile(filePath, "utf8");
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  private async loadPendingWrites(
    threadId: string,
    checkpointId: string
  ): Promise<Array<[string, string, unknown]>> {
    const writesDir = this.writesDir(threadId, checkpointId);
    try {
      const entries = await fs.readdir(writesDir);
      const files = entries.filter((f) => f.endsWith(".json")).sort();
      const out: Array<[string, string, unknown]> = [];
      for (const file of files) {
        const rec = await this.readJson(path.join(writesDir, file));
        if (!rec) continue;
        const value = await this.decodeValue(rec);
        out.push([String(rec.task_id), String(rec.channel), value]);
      }
      return out;
    } catch {
      return [];
    }
  }

  override getNextVersion(current: number | undefined): number {
    return (current ?? 0) + 1;
  }

  async getTuple(config: RunnableConfig): Promise<CheckpointTuple | undefined> {
    const cfg = config.configurable ?? {};
    const threadId = String(cfg.thread_id ?? "");
    const ns = String(cfg.checkpoint_ns ?? "");
    const checkpointId = getCheckpointId(config);

    const cpDir = this.checkpointDir(threadId, ns);
    let data: Record<string, unknown> | null = null;

    if (checkpointId) {
      data = await this.readJson(this.checkpointPath(threadId, ns, checkpointId));
      if (!data) return undefined;
    } else {
      try {
        const files = (await fs.readdir(cpDir))
          .filter((f) => f.endsWith(".json"))
          .sort()
          .reverse();
        if (files.length === 0) return undefined;
        data = await this.readJson(path.join(cpDir, files[0]));
        if (!data) return undefined;
      } catch {
        return undefined;
      }
    }

    const checkpoint = await this.unpackCheckpoint(
      data.checkpoint as Record<string, unknown>
    );
    const pendingWrites = await this.loadPendingWrites(threadId, checkpoint.id);

    return {
      config: data.config as RunnableConfig,
      checkpoint,
      metadata: (data.metadata as CheckpointMetadata) ?? {},
      parentConfig: (data.parent_config as RunnableConfig) ?? undefined,
      pendingWrites,
    };
  }

  async *list(
    config: RunnableConfig,
    options?: CheckpointListOptions
  ): AsyncGenerator<CheckpointTuple> {
    const cfg = config.configurable ?? {};
    const threadId = String(cfg.thread_id ?? "");
    const ns = String(cfg.checkpoint_ns ?? "");
    const beforeId = options?.before ? getCheckpointId(options.before) : null;

    const cpDir = this.checkpointDir(threadId, ns);
    let files: string[] = [];
    try {
      files = (await fs.readdir(cpDir))
        .filter((f) => f.endsWith(".json"))
        .sort()
        .reverse();
    } catch {
      return;
    }

    let count = 0;
    for (const file of files) {
      if (options?.limit !== undefined && count >= options.limit) break;
      const data = await this.readJson(path.join(cpDir, file));
      if (!data) continue;

      const checkpoint = await this.unpackCheckpoint(
        data.checkpoint as Record<string, unknown>
      );

      if (beforeId && checkpoint.id >= beforeId) continue;

      if (options?.filter) {
        const meta = (data.metadata ?? {}) as Record<string, unknown>;
        const match = Object.entries(options.filter).every(
          ([k, v]) => meta[k] === v
        );
        if (!match) continue;
      }

      const pendingWrites = await this.loadPendingWrites(threadId, checkpoint.id);

      yield {
        config: data.config as RunnableConfig,
        checkpoint,
        metadata: (data.metadata as CheckpointMetadata) ?? {},
        parentConfig: (data.parent_config as RunnableConfig) ?? undefined,
        pendingWrites,
      };
      count += 1;
    }
  }

  async put(
    config: RunnableConfig,
    checkpoint: Checkpoint,
    metadata: CheckpointMetadata,
    _newVersions: Record<string, unknown>
  ): Promise<RunnableConfig> {
    const cfg = config.configurable ?? {};
    const threadId = String(cfg.thread_id ?? "");
    const ns = String(cfg.checkpoint_ns ?? "");
    const parentId = getCheckpointId(config) || undefined;
    const checkpointId = checkpoint.id;

    const savedConfig: RunnableConfig = {
      configurable: {
        thread_id: threadId,
        checkpoint_ns: ns,
        checkpoint_id: checkpointId,
      },
    };

    const parentConfig: RunnableConfig | null = parentId
      ? {
          configurable: {
            thread_id: threadId,
            checkpoint_ns: ns,
            checkpoint_id: parentId,
          },
        }
      : null;

    await this.writeJson(this.checkpointPath(threadId, ns, checkpointId), {
      config: savedConfig,
      checkpoint: await this.packCheckpoint(checkpoint),
      metadata,
      parent_config: parentConfig,
    });

    return savedConfig;
  }

  async putWrites(
    config: RunnableConfig,
    writes: PendingWrite[],
    taskId: string
  ): Promise<void> {
    const cfg = config.configurable ?? {};
    const threadId = String(cfg.thread_id ?? "");
    const checkpointId = String(cfg.checkpoint_id ?? "");
    const writesDir = this.writesDir(threadId, checkpointId);

    await fs.mkdir(writesDir, { recursive: true });

    for (let idx = 0; idx < writes.length; idx += 1) {
      const [channel, value] = writes[idx];
      const rec = await this.encodeValue(value);
      (rec as Record<string, unknown>).task_id = taskId;
      (rec as Record<string, unknown>).idx = idx;
      (rec as Record<string, unknown>).channel = channel;
      const filePath = path.join(
        writesDir,
        `${taskId}-${String(idx).padStart(4, "0")}.json`
      );
      await this.writeJson(filePath, rec as Record<string, unknown>);
    }
  }

  async deleteThread(threadId: string): Promise<void> {
    const td = this.threadDir(threadId);
    await fs.rm(td, { recursive: true, force: true });
  }
}
