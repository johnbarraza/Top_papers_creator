"""Quick test of the Agent SDK."""
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async def test():
    print("Starting SDK test...")
    opts = ClaudeAgentOptions(permission_mode="dontAsk", max_turns=1)
    async for msg in query(prompt="Respond only with: OK", options=opts):
        if isinstance(msg, ResultMessage):
            print(f"RESULT: {msg.result}")
    print("DONE")

asyncio.run(test())
