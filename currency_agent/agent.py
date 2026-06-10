import logging
import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

load_dotenv()

SYSTEM_INSTRUCTION = (
    "You are a specialized assistant for currency conversions, powered by the "
    "AllRatesToday exchange rate API (https://allratestoday.com). "
    "Your sole purpose is to use the 'get_exchange_rate', 'compare_rates', "
    "'get_historical_rates', 'get_rate_change' and 'list_currencies' tools to answer "
    "questions about currency exchange rates. "
    "When the user asks to convert a specific amount, pass it as the 'amount' argument "
    "to get_exchange_rate instead of doing the arithmetic yourself. "
    "When the user asks whether a rate went up or down, use get_rate_change. "
    "If the user asks about anything other than currency conversion or exchange rates, "
    "politely state that you cannot help with that topic and can only assist with currency-related queries. "
    "Do not attempt to answer unrelated questions or use tools for other purposes."
)


def resolve_model():
    """Resolve the agent model from the MODEL env var.

    Gemini models are passed straight to ADK; anything else (e.g.
    "anthropic/claude-sonnet-4-6", "openai/gpt-4o") is routed through LiteLLM.
    """
    name = os.getenv("MODEL", "gemini-2.5-flash")
    if name.startswith("gemini"):
        return name
    try:
        from google.adk.models.lite_llm import LiteLlm
    except ImportError as e:
        raise RuntimeError(
            f"MODEL={name} requires LiteLLM. Install it with: pip install litellm"
        ) from e
    logger.info(f"--- 🔀 Using non-Gemini model via LiteLLM: {name} ---")
    return LiteLlm(model=name)


logger.info("--- 🔧 Loading MCP tools from MCP Server... ---")
logger.info("--- 🤖 Creating ADK Currency Agent... ---")

root_agent = LlmAgent(
    model=resolve_model(),
    name="currency_agent",
    description=(
        "An agent that answers currency questions using live AllRatesToday data: "
        "conversions, multi-currency comparisons, historical rates and trends."
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp")
            )
        )
    ],
)

# Make the agent A2A-compatible
a2a_app = to_a2a(root_agent, port=10000)
