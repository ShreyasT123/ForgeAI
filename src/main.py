# import os
# from langgraph.checkpoint.memory import MemorySaver
# from deepagents import create_deep_agent

# # Your custom tool modules
# from helius_agent.tools.files import FS_TOOLS
# from helius_agent.tools.shell import SHELL_TOOLS
# from helius_agent.tools.git import GIT_TOOLS
# from helius_agent.tools.skills import SKILLS_TOOLS
# # Integrations
# from helius_agent.observability.trace import AuditTelemetryHandler
# from helius_agent.agents.hitl import handle_hitl_interrupt
# import dotenv
# dotenv.load_dotenv()
# def run_agent():
#     # 1. Setup Configuration
#     thread_id = "dev-session-001"
#     config = {
#         "configurable": {"thread_id": thread_id},
#         # Telemetry is automatically propagated to all tools/LLM calls
#         "callbacks": [AuditTelemetryHandler(session_id=thread_id)]
#     }

#     # 2. Initialize Agent
#     # We combine all tool lists into one flat list
#     all_tools = FS_TOOLS + SHELL_TOOLS + GIT_TOOLS + SKILLS_TOOLS
    
#     agent_graph = create_deep_agent(
#         model="google_genai:gemini-2.5-flash",
#         tools=all_tools,
#         system_prompt=(
#             "You are an expert AI software engineer. "
#             "Use your tools to navigate, edit, and manage the repository. "
#             "Always verify your changes with Git and use Skills to maintain coding standards."
#         ),
#         # MemorySaver enables HITL persistence
#         checkpointer=MemorySaver() 
#     )

#     # 3. Execution Loop
#     print(f"Agent Initialized. Thread: {thread_id}")
    
#     # Example task
#     user_input = "Initialize a new node project called `nextpress` and install express and api hello world api if u can initialise a git repo"
    
#     # Run the graph
#     result = agent_graph.invoke(
#         {"messages": [("user", user_input)]},
#         config=config
#     )

#     # 4. HITL Interruption Handler
#     # This loop keeps the agent alive even if it hits a 'dangerous' tool
#     while agent_graph.get_state(config).next:
#         # handle_hitl_interrupt handles the approval/rejection and resumes the graph
#         result = handle_hitl_interrupt(agent_graph, config, interactive=True)
#         if not result: break

#     # Final Output
#     print(result["messages"])

# if __name__ == "__main__":
#     # Ensure environment variables are set
#     run_agent()
import traceback
import time
import dotenv

from langgraph.checkpoint.memory import MemorySaver
from deepagents import create_deep_agent

# Your custom tool modules
from helius_agent.tools.files import FS_TOOLS
from helius_agent.tools.shell import SHELL_TOOLS
from helius_agent.tools.git import GIT_TOOLS
from helius_agent.tools.skills import SKILLS_TOOLS

# Integrations
from helius_agent.observability.trace import AuditTelemetryHandler
from helius_agent.agents.hitl import handle_hitl_interrupt

dotenv.load_dotenv()


def run_agent(max_retries: int = 3):
    thread_id = "dev-session-001"

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [AuditTelemetryHandler(session_id=thread_id)],
    }

    all_tools = FS_TOOLS + SHELL_TOOLS + GIT_TOOLS + SKILLS_TOOLS

    agent_graph = create_deep_agent(
        model="google_genai:gemini-2.5-flash",
        tools=all_tools,
        system_prompt=(
            "You are an expert AI software engineer. "
            "Use your tools to navigate, edit, and manage the repository. "
            "Always verify your changes with Git and use Skills to maintain coding standards."
        ),
        checkpointer=MemorySaver(),
    )

    print(f"\n🚀 Agent Initialized | Thread: {thread_id}\n")

    user_input = (
        "Initialize a new node project called `nextpress` and install express "
        "and api hello world api if u can initialise a git repo"
    )

    attempt = 0

    while attempt < max_retries:
        try:
            print(f"\n🧠 Attempt {attempt + 1}/{max_retries}")

            # --- Initial Run ---
            result = agent_graph.invoke(
                {"messages": [("user", user_input)]},
                config=config,
            )

            # --- HITL Loop ---
            while True:
                state = agent_graph.get_state(config)

                if not state.next:
                    break

                print("\n⚠️ HITL Interrupt detected...")

                result = handle_hitl_interrupt(
                    agent_graph,
                    config,
                    interactive=True
                )

                if not result:
                    print("❌ Execution stopped by user / handler.")
                    return

            # --- Success ---
            print("\n✅ Final Output:\n")
            print(result["messages"])
            return

        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user. Exiting safely.")
            return

        except Exception as e:
            attempt += 1

            print("\n💥 ERROR OCCURRED")
            print("-" * 50)
            print(f"Error Type: {type(e).__name__}")
            print(f"Error Message: {str(e)}\n")

            print("📜 Full Traceback:\n")
            traceback.print_exc()

            print("-" * 50)

            if attempt < max_retries:
                print(f"\n🔁 Retrying in 2 seconds...\n")
                time.sleep(2)
            else:
                print("\n❌ Max retries reached. Exiting.")
                return


if __name__ == "__main__":
    run_agent()