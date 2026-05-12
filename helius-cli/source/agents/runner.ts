import { randomUUID } from "node:crypto";

import { getSettings } from "../utils/config.js";
import { getLogger } from "../utils/logger.js";
import { handleHitlInterrupt, HITLPresenter } from "./hitl.js";
import { logAudit } from "../utils/audit.js";


const logger = getLogger("agents.runner");
const isSilent = process.env.HELIUS_SILENT === "true";

function log(msg: string) {
  if (!isSilent) console.log(msg);
}

function newThreadId(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}`;
}

function buildRunConfig(threadId: string): Record<string, unknown> {
  return {
    configurable: { thread_id: threadId },
  };
}

function printLastMessage(result: Record<string, unknown>): void {
  if (isSilent) return;
  const messages = result.messages as Array<any> | undefined;
  if (!messages || messages.length === 0) return;
  const last = messages[messages.length - 1];
  
  let content = last?.content;
  if (Array.isArray(content)) {
    content = content
      .map((block: any) => {
        if (typeof block === "string") return block;
        if (block?.text) return block.text;
        if (block?.type === "text") return block.text;
        return "";
      })
      .join("");
  } else if (content && typeof content === "object") {
    content = content.text ?? JSON.stringify(content);
  }

  if (content !== undefined && content !== null && String(content).trim().length > 0) {
    console.log(String(content));
  }
}

export async function runAgent(
  userInput: string,
  opts: {
    agent: any;
    presenter?: HITLPresenter;
    threadId?: string | null;
  }
): Promise<{ result: Record<string, unknown> | null; threadId: string }> {
  const settings = getSettings();
  const maxRetries = settings.agent.max_retries;
  const retryDelay = settings.agent.retry_delay_seconds;

  const tid = opts.threadId ?? newThreadId(settings.agent.thread_id_prefix);
  const isResumed = Boolean(opts.threadId);
  const config = buildRunConfig(tid);

  logger.info(
    `runAgent start thread=${tid} resumed=${isResumed} retries=${maxRetries}`
  );

  if (isResumed) {
    log(`\nResuming session | Thread: ${tid}\n`);
    logAudit(tid, "agent_resume", { userInput });
  } else {
    log(`\nAgent started | Thread: ${tid}\n`);
    logAudit(tid, "agent_start", { userInput });
  }

  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    try {
      logger.info(`attempt ${attempt}/${maxRetries} thread=${tid}`);
      log(`Attempt ${attempt}/${maxRetries}`);
      let result = await opts.agent.invoke(
        { messages: [{ role: "user", content: userInput }] },
        config
      );
      logger.info(`invoke done thread=${tid}`);

      while (true) {
        const state = await opts.agent.getState(config);
        if (!state?.next || state.next.length === 0) break;
        log("\nHuman authorization required...");
        logger.info(`HITL interrupt thread=${tid}`);

        result = await handleHitlInterrupt(opts.agent, config, opts.presenter);
        if (!result) {
          log("Execution stopped (HITL handler returned nothing).");
          logger.warn(`HITL returned null thread=${tid}`);
          return { result: null, threadId: tid };
        }
      }

      log(`\nTask complete. (session: ${tid})\n`);
      logger.info(`runAgent success thread=${tid}`);
      logAudit(tid, "agent_success", { result });
      printLastMessage(result as Record<string, unknown>);
      return { result: result as Record<string, unknown>, threadId: tid };
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        log("\nInterrupted by user.");
        logger.warn(`runAgent aborted thread=${tid}`);
        return { result: null, threadId: tid };
      }

      log(`\nError on attempt ${attempt}/${maxRetries}`);
      logger.error(`runAgent error attempt=${attempt} thread=${tid}`, err);
      logAudit(tid, "agent_error", { attempt, error: (err as Error).message });
      if (attempt < maxRetries) {
        log(`\nRetrying in ${retryDelay}s...`);
        await new Promise((r) => setTimeout(r, retryDelay * 1000));
      } else {
        log("\nAll retries exhausted.");
        return { result: null, threadId: tid };
      }
    }
  }

  return { result: null, threadId: tid };
}
