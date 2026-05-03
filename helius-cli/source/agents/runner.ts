import { randomUUID } from "node:crypto";

import { getSettings } from "../utils/config.js";
import { getLogger } from "../utils/logger.js";
import { handleHitlInterrupt, HITLPresenter } from "./hitl.js";
import { logAudit } from "../utils/audit.js";


const logger = getLogger("agents.runner");

function newThreadId(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}`;
}

function buildRunConfig(threadId: string): Record<string, unknown> {
  return {
    configurable: { thread_id: threadId },
  };
}

function printLastMessage(result: Record<string, unknown>): void {
  const messages = result.messages as Array<any> | undefined;
  if (!messages || messages.length === 0) return;
  const last = messages[messages.length - 1];
  const content = last?.content ?? last?.content?.text ?? last?.content;
  if (content !== undefined && content !== null) {
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
    console.log(`\nResuming session | Thread: ${tid}\n`);
    logAudit(tid, "agent_resume", { userInput });
  } else {
    console.log(`\nAgent started | Thread: ${tid}\n`);
    logAudit(tid, "agent_start", { userInput });
  }

  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    try {
      logger.info(`attempt ${attempt}/${maxRetries} thread=${tid}`);
      console.log(`Attempt ${attempt}/${maxRetries}`);
      let result = await opts.agent.invoke(
        { messages: [{ role: "user", content: userInput }] },
        config
      );
      logger.info(`invoke done thread=${tid}`);

      while (true) {
        const state = await opts.agent.getState(config);
        if (!state?.next || state.next.length === 0) break;
        console.log("\nHuman authorization required...");
        logger.info(`HITL interrupt thread=${tid}`);

        result = await handleHitlInterrupt(opts.agent, config, opts.presenter);
        if (!result) {
          console.log("Execution stopped (HITL handler returned nothing).");
          logger.warn(`HITL returned null thread=${tid}`);
          return { result: null, threadId: tid };
        }
      }

      console.log(`\nTask complete. (session: ${tid})\n`);
      logger.info(`runAgent success thread=${tid}`);
      logAudit(tid, "agent_success", { result });
      printLastMessage(result as Record<string, unknown>);
      return { result: result as Record<string, unknown>, threadId: tid };
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        console.log("\nInterrupted by user.");
        logger.warn(`runAgent aborted thread=${tid}`);
        return { result: null, threadId: tid };
      }

      console.log(`\nError on attempt ${attempt}/${maxRetries}`);
      logger.error(`runAgent error attempt=${attempt} thread=${tid}`, err);
      logAudit(tid, "agent_error", { attempt, error: (err as Error).message });
      if (attempt < maxRetries) {
        console.log(`\nRetrying in ${retryDelay}s...`);
        await new Promise((r) => setTimeout(r, retryDelay * 1000));
      } else {
        console.log("\nAll retries exhausted.");
        return { result: null, threadId: tid };
      }
    }
  }

  return { result: null, threadId: tid };
}
