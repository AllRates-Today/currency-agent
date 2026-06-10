"""A2A client for the travel budget agent (multi-agent demo).

Requires the full chain running:
  1. MCP server        — uv run mcp-server/server.py            (port 8080)
  2. Currency agent    — uv run uvicorn currency_agent.agent:a2a_app --port 10000
  3. Travel agent      — uv run uvicorn travel_agent.agent:a2a_app --port 10001
"""

import os
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

AGENT_URL = os.getenv("TRAVEL_AGENT_URL", "http://localhost:10001")

QUESTION = (
    "I have 2000 USD for a 5-day trip to Japan. "
    "What is my total and daily budget in JPY?"
)


def create_send_message_payload(text: str) -> dict[str, Any]:
    return {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": uuid4().hex,
        },
    }


async def main() -> None:
    print(f"--- 🔄 Connecting to travel agent at {AGENT_URL}... ---")
    async with httpx.AsyncClient(timeout=300) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=AGENT_URL)
        agent_card = await resolver.get_agent_card()
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)
        print("--- ✅ Connection successful. ---")

        print(f"--- ✉️  Question: {QUESTION} ---")
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**create_send_message_payload(QUESTION)),
        )
        response = await client.send_message(request)
        if hasattr(response, "root"):
            print(response.root.model_dump_json(exclude_none=True))
        else:
            print(response.model_dump(mode="json", exclude_none=True))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
