import test from "ava";
import { buildAgent } from "../../source/agents/builder.js";
import { MemorySaver } from "@langchain/langgraph";

test("buildAgent constructs an agent with tools", async (t) => {
  const agent = await buildAgent([], {
    checkpointer: new MemorySaver(),
    systemPrompt: "test prompt",
  });
  t.truthy(agent);
  t.is(typeof agent.invoke, "function");
});
