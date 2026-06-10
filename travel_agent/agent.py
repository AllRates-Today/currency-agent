"""Travel budget agent — a second A2A agent that delegates all currency math
to the currency agent over the A2A protocol. Demonstrates agent-to-agent
collaboration: run the currency agent first (port 10000), then this one
(port 10001)."""

import logging
import os
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.a2a.utils.agent_to_a2a import to_a2a

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

load_dotenv()

CURRENCY_AGENT_URL = os.getenv("CURRENCY_AGENT_URL", "http://localhost:10000")

SYSTEM_INSTRUCTION = (
    "You are a travel budget planner. You help users figure out what their travel "
    "budget is worth in the local currency of their destination and how to split it "
    "per day. You do NOT know exchange rates yourself — for ANY question involving "
    "exchange rates or currency conversion, you MUST call the 'ask_currency_agent' "
    "tool with a clear, self-contained question (e.g. 'How much is 2000 USD in JPY?'). "
    "Then use its answer to build the budget breakdown."
)


def _collect_text(value: Any, out: list[str]) -> None:
    """Recursively collect every 'text' field from an A2A response payload."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "text" and isinstance(item, str):
                out.append(item)
            else:
                _collect_text(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_text(item, out)


async def ask_currency_agent(question: str) -> str:
    """Ask the currency agent an exchange-rate question over the A2A protocol.

    Args:
        question: A self-contained currency question, e.g.
            "How much is 2000 USD in JPY?" or "Is EUR up or down vs USD this week?"

    Returns:
        The currency agent's answer as plain text.
    """
    logger.info(f"--- 🤝 A2A: asking currency agent: {question} ---")
    async with httpx.AsyncClient(timeout=120) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=CURRENCY_AGENT_URL)
        agent_card = await resolver.get_agent_card()
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": question}],
                "messageId": uuid4().hex,
            },
        }
        request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
        response = await client.send_message(request)

        dump = (
            response.root.model_dump(mode="json", exclude_none=True)
            if hasattr(response, "root")
            else response.model_dump(mode="json", exclude_none=True)
        )
        texts: list[str] = []
        _collect_text(dump, texts)
        answer = "\n".join(t for t in texts if t.strip() and t.strip() != question.strip())
        logger.info(f"--- 🤝 A2A: currency agent answered ({len(answer)} chars) ---")
        return answer or "No answer received from the currency agent."


root_agent = LlmAgent(
    model=os.getenv("MODEL", "gemini-2.5-flash"),
    name="travel_budget_agent",
    description=(
        "A travel budget planner that delegates exchange-rate questions to the "
        "currency agent via the A2A protocol."
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[ask_currency_agent],
)

# Expose this agent over A2A too (on its own port)
a2a_app = to_a2a(root_agent, port=10001)
