# AllRatesToday Currency Agent — currency-agent

A runnable sample app showing **A2A + Google ADK + MCP** working together: an AI agent that answers currency questions using live exchange rate data from [AllRatesToday](https://allratestoday.com). Built for developers who want a concrete, working reference for wiring an MCP tool server to an ADK agent and exposing it over the Agent2Agent protocol.

[![CI](https://github.com/AllRates-Today/currency-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/AllRates-Today/currency-agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Powered by AllRatesToday](https://img.shields.io/badge/Powered%20by-AllRatesToday-orange.svg)](https://allratestoday.com)

It uses the **Agent2Agent (A2A) Python SDK** ([`a2a-sdk`](https://github.com/a2aproject/a2a-python)), Google's **Agent Development Kit** ([`google-adk`](https://github.com/google/adk-python)), and a [FastMCP](https://github.com/jlowin/fastmcp) server that exposes live, historical and reference exchange rate data. Rates come from institutional interbank market data.

![Architecture Overview](images/architecture.png)

## 🚀 Features

- 🛠️ **Five MCP tools** — live rates, multi-currency comparison, history, trend and the currency list
- 🤖 **ADK agent** — an `LlmAgent` that loads the MCP tools over streamable HTTP and decides which to call
- 🤝 **A2A server** — the agent is wrapped with `to_a2a()` so other agents can call it as a peer
- 🧳 **Multi-agent demo** — a second travel-budget agent with no rate tools of its own, delegating over A2A
- 💾 **Caching, timeouts, retries** — 5-minute TTL on rates, 24-hour TTL on the currency list, 10s timeout, 3 attempts with exponential backoff on `429/500/502/503/504`
- 🔀 **Model-agnostic** — Gemini by default; Claude or GPT via LiteLLM
- 🐳 **Docker Compose** — MCP server + agent in two containers
- ✅ **Unit tested in CI** — tests mock `httpx`, so they need no API key

## 🔑 Get your API key

- Free AllRatesToday API key (no card required): [allratestoday.com/register](https://allratestoday.com/register)
- A **Google AI Studio API key** for the default `gemini-2.5-flash` model (or a LiteLLM-supported key — see [Using other models](#using-other-models))

> Both keys are yours to supply. Nothing in this repo ships credentials, and the end-to-end agent run cannot be exercised in CI — CI only runs lint plus the mocked unit tests. Treat the live agent flow as something to verify in your own environment.

## 📦 Installation

```bash
git clone https://github.com/AllRates-Today/currency-agent.git
cd currency-agent
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation) (used to manage dependencies):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Configure environment variables:

```bash
cp .env.example .env
# then edit .env and set ALLRATES_API_KEY and GOOGLE_API_KEY
```

`currency_agent/agent.py` and `travel_agent/agent.py` call `load_dotenv()`, so `.env` is picked up automatically. The MCP server reads plain environment variables, so export them in its terminal.

## 🏁 Quick start

Three terminals:

**Terminal 1 — MCP server** (port `8080`):

```bash
export $(grep -v '^#' .env | xargs)  # or rely on your shell env
uv run mcp-server/server.py
```

**Terminal 2 — A2A server (ADK agent)** (port `10000`):

```bash
uv run uvicorn currency_agent.agent:a2a_app --host localhost --port 10000
```

**Terminal 3 — A2A client:**

```bash
uv run currency_agent/test_client.py
```

The client runs a single-turn request (*"how much is 100 USD in CAD?"*) and then a multi-turn request (*"how much is 100 USD?"* → *"in GBP"*), printing the raw A2A JSON for each.

### With Docker Compose

```bash
ALLRATES_API_KEY=art_live_... GOOGLE_API_KEY=... docker compose up --build
# then, in another terminal:
uv run currency_agent/test_client.py
```

Compose builds two services — `mcp-server` (from `mcp-server/Dockerfile`) and `agent` (from the root `Dockerfile`) — and points the agent at `http://mcp-server:8080/mcp`. The travel agent is not part of the Compose stack; run it locally as shown below.

### Example queries

- *"How much is 500 USD in LKR?"*
- *"Compare USD against EUR, GBP and JPY."*
- *"Is the euro up or down against the dollar this week?"*
- *"Show me the USD/EUR trend over the last 30 days."*
- *"Do you support the Sri Lankan rupee?"*

The agent's system instruction restricts it to currency topics; it will decline anything else.

## 📚 MCP tool reference

All five tools live in `mcp-server/server.py` and are served over the streamable HTTP transport at `http://localhost:8080/mcp`. Every tool returns a plain dict, or `{"error": "..."}` when the call fails — no exceptions are raised at the tool boundary.

| Tool | Arguments (defaults) | Returns |
|---|---|---|
| `get_exchange_rate` | `currency_from="USD"`, `currency_to="EUR"`, `amount=None` | `{from, to, rate, source}`, plus `amount` and `converted` (rounded to 4dp) when `amount` is given |
| `compare_rates` | `currency_from="USD"`, `currency_to_list="EUR,GBP,JPY"` | `{base, rates: {CODE: rate, …}}`, plus `errors` per target that failed. Comma-separated list, capped at **10 targets** |
| `get_historical_rates` | `currency_from="USD"`, `currency_to="EUR"`, `period="7d"` | The API's historical payload — a list of `{date, rate}` points |
| `get_rate_change` | `currency_from="USD"`, `currency_to="EUR"`, `period="7d"` | `{from, to, period, start_date, start_rate, end_date, end_rate, change, change_pct, direction}` where `direction` is `up`/`down`/`flat` |
| `list_currencies` | none | `{currencies: [{code, name, symbol}, …], count}` — 150+ ISO 4217 fiat currencies |

**Valid periods:** `1d`, `7d`, `30d`, `1y`. Anything else returns an error without hitting the API.

**Endpoints used:** `get_exchange_rate` and `compare_rates` call `/rate`; `get_historical_rates` and `get_rate_change` call `/historical-rates`; `list_currencies` calls `/v1/symbols` — all relative to `ALLRATES_BASE_URL`.

Sanity-check a running MCP server directly, without the agent:

```bash
uv run mcp-server/test_server.py
```

It lists the tools and calls `get_exchange_rate` for USD → EUR.

## 🤝 Multi-agent demo (A2A in action)

`travel_agent/` contains a second agent — a **travel budget planner** — with no exchange-rate tools of its own. Its only tool is `ask_currency_agent(question)`, which resolves the currency agent's A2A agent card and sends it a message over the A2A protocol. That is the actual point of A2A: agents consuming other agents as peers, not as bundled tools.

With Terminals 1 and 2 from above still running:

```bash
# Terminal 3 — travel agent (A2A server on port 10001)
uv run uvicorn travel_agent.agent:a2a_app --host localhost --port 10001

# Terminal 4 — ask it something
uv run travel_agent/test_client.py
```

The client sends a fixed question: *"I have 2000 USD for a 5-day trip to Japan. What is my total and daily budget in JPY?"* The travel agent asks the currency agent for the rate, then does the budget breakdown itself.

Note that the travel agent reads `MODEL` directly and passes it to ADK — unlike the currency agent, it has no LiteLLM fallback, so keep it on a Gemini model.

## ⚙️ Configuration

| Env var | Default | Used by | Description |
|---|---|---|---|
| `ALLRATES_API_KEY` | — (required) | MCP server | Your AllRatesToday API key. Missing key → every tool returns an error telling you to register |
| `GOOGLE_API_KEY` | — | Both agents | Google AI Studio key, required for Gemini models |
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` | Both agents | Set `TRUE` to use Vertex AI instead (then also set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`) |
| `MODEL` | `gemini-2.5-flash` | Both agents | Agent model — see below |
| `MCP_SERVER_URL` | `http://localhost:8080/mcp` | Currency agent | Where the agent finds the MCP server |
| `CURRENCY_AGENT_URL` | `http://localhost:10000` | Travel agent | Where the travel agent finds the currency agent |
| `ALLRATES_BASE_URL` | `https://allratestoday.com/api` | MCP server | API base URL override |
| `PORT` | `8080` | MCP server | MCP server listen port (binds `0.0.0.0`) |
| `AGENT_URL` | `http://localhost:10000` | `currency_agent/test_client.py` | Agent the test client connects to |
| `TRAVEL_AGENT_URL` | `http://localhost:10001` | `travel_agent/test_client.py` | Travel agent the test client connects to |

### Using other models

Non-Gemini models are routed through [LiteLLM](https://github.com/BerriAI/litellm). This applies to the **currency agent only**:

```bash
uv pip install litellm   # or: pip install 'allratestoday-currency-agent[litellm]'
export MODEL=anthropic/claude-sonnet-4-6 ANTHROPIC_API_KEY=sk-ant-...
# or: export MODEL=openai/gpt-4o OPENAI_API_KEY=sk-...
```

Any `MODEL` value not starting with `gemini` is wrapped in `LiteLlm`; if LiteLLM is not installed, the agent raises a clear error at import time.

## 🛡️ Error handling

The MCP server never throws at the tool boundary — it returns a dict with an `error` key, so the model can read and explain the failure.

| Situation | Behaviour |
|---|---|
| `ALLRATES_API_KEY` unset | `{"error": "ALLRATES_API_KEY is not set…"}` before any network call |
| `429`, `500`, `502`, `503`, `504` | Retried up to 3 attempts with 0.5s / 1s backoff, then surfaced |
| Other `4xx`/`5xx` | Returned immediately as `API error: <message from body>` (falls back to `HTTP <code>`) |
| Network / connection failure | Retried, then `API request failed after 3 attempts (…)` |
| Non-JSON body | `Invalid JSON response from API.` |
| Invalid `period` | Rejected locally with the list of valid periods |
| Too few history points | `Not enough data points for <PAIR> over <period>.` |

## 🧪 Development

```bash
uv pip install fastmcp==2.11.3 httpx pytest ruff
pytest                            # unit tests — httpx is mocked, no API key needed
ruff check mcp-server tests       # lint (same scope as CI)
uv run mcp-server/test_server.py  # integration check against a running MCP server
```

CI (`.github/workflows/ci.yml`) runs lint plus `pytest` on Python 3.10 and 3.12 for every push to `main` and every pull request. It does not run the agents, so the end-to-end A2A flow is not covered by automated tests.

## 💡 Notes

- The rate cache is a plain in-process dict — it is per MCP-server process and is lost on restart. It is there to save API quota, not as a durable cache.
- `compare_rates` issues one request per target currency (up to 10), each subject to the same caching and retry logic.
- The MCP server binds `0.0.0.0` and honours `PORT`, which makes it directly deployable to Cloud Run or a similar container host.
- If you only want exchange-rate tools inside Claude Desktop or Cursor — no ADK, no A2A — use the production MCP server package instead:

  ```json
  {
    "mcpServers": {
      "allratestoday": {
        "command": "npx",
        "args": ["-y", "@allratestoday/mcp-server"],
        "env": { "ALLRATES_API_KEY": "art_live_..." }
      }
    }
  }
  ```

## 🙏 Acknowledgements

Based on the [jackwotherspoon/currency-agent](https://github.com/jackwotherspoon/currency-agent) sample (Apache 2.0), adapted to use the AllRatesToday API.

## 🔗 Links

- **Website:** [allratestoday.com](https://allratestoday.com)
- **API Docs:** [allratestoday.com/docs](https://allratestoday.com/docs)
- **Free API key:** [allratestoday.com/register](https://allratestoday.com/register)
- **Developer Guide:** [allratestoday.com/developers](https://allratestoday.com/developers)
- **Status:** [allratestoday.com/status](https://allratestoday.com/status)
- **Support:** [allratestoday.com/contact](https://allratestoday.com/contact)
- **MCP server:** [AllRates-Today/mcp-server](https://github.com/AllRates-Today/mcp-server) · [@allratestoday/mcp-server](https://www.npmjs.com/package/@allratestoday/mcp-server)

## 📜 License

[MIT](LICENSE)
