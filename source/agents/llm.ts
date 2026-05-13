import { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BaseMessage } from "@langchain/core/messages";
import type { ChatResult } from "@langchain/core/outputs";
import { ChatGroq } from "@langchain/groq";

import { getLogger } from "../utils/logger.js";

const logger = getLogger("agents.llm");

export function makeDefaultModels(): BaseChatModel[] {
  return [
    new ChatGroq({ model: "openai/gpt-oss-20b" }),
  ];
}

export type RotationStrategy = "round_robin" | "fallback" | "random";

export class RotatingChatModel extends BaseChatModel {
  llmModels: BaseChatModel[];
  strategy: RotationStrategy;
  debug: boolean;
  idx: number;

  constructor(opts?: {
    models?: BaseChatModel[];
    strategy?: RotationStrategy;
    debug?: boolean;
  }) {
    super({});
    this.llmModels = opts?.models ?? makeDefaultModels();
    this.strategy = opts?.strategy ?? "round_robin";
    this.debug = opts?.debug ?? true;
    this.idx = 0;
  }

  _llmType(): string {
    return "rotating-chat-model";
  }

  private modelLabel(model: BaseChatModel): string {
    const anyModel = model as any;
    return (
      anyModel.modelName ||
      anyModel.model ||
      anyModel.model_id ||
      model.constructor?.name ||
      "UnknownModel"
    );
  }

  private debugPrint(message: string): void {
    if (this.debug) {
      logger.info(message);
    }
  }

  private candidateIndices(): number[] {
    const n = this.llmModels.length;
    if (n === 0) {
      throw new Error("RotatingChatModel requires at least one underlying model.");
    }
    if (this.strategy === "fallback") {
      return Array.from({ length: n }, (_, i) => i);
    }
    if (this.strategy === "round_robin") {
      const start = this.idx;
      this.idx = (this.idx + 1) % n;
      return Array.from({ length: n }, (_, i) => (start + i) % n);
    }
    if (this.strategy === "random") {
      const indices = Array.from({ length: n }, (_, i) => i);
      for (let i = indices.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [indices[i], indices[j]] = [indices[j], indices[i]];
      }
      return indices;
    }
    throw new Error(`Unsupported strategy: ${this.strategy}`);
  }

  async _generate(
    messages: BaseMessage[],
    options: this["ParsedCallOptions"],
    runManager?: any
  ): Promise<ChatResult> {
    const errors: string[] = [];

    for (const idx of this.candidateIndices()) {
      const model = this.llmModels[idx];
      const label = this.modelLabel(model);
      try {
        logger.info(`llm try model=${label}`);
        const gen = await (model as any)._generate(messages, options, runManager);
        logger.info(`llm success model=${label}`);
        return gen as ChatResult;
      } catch (err) {
        errors.push(`${label}: ${(err as Error).name}: ${(err as Error).message}`);
        this.debugPrint(`Model failed: ${label} -> ${(err as Error).message}`);
        logger.error(`llm failed model=${label}`, err);
      }
    }

    throw new Error(`All underlying models failed:\n${errors.join("\n")}`);
  }
}
