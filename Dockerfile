# A2A server (ADK currency agent)
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "a2a-sdk==0.3.3" \
    "fastmcp==2.11.3" \
    "google-adk==1.13.0" \
    "google-genai>=1.17.0" \
    "httpx>=0.27.0" \
    "python-dotenv>=1.1.0" \
    "uvicorn>=0.30.0"

COPY currency_agent ./currency_agent

EXPOSE 10000

CMD ["uvicorn", "currency_agent.agent:a2a_app", "--host", "0.0.0.0", "--port", "10000"]
