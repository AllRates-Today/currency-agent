FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "fastmcp==2.11.3" "httpx>=0.27.0"

COPY server.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
