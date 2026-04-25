FROM mcr.microsoft.com/playwright:v1.59.0-jammy

RUN apt-get update && apt-get install -y python3-pip curl && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir httpx starlette uvicorn

RUN npm install -g @playwright/mcp@latest

RUN mkdir -p /app /profiles /audit
COPY browser_mcp.py /app/browser_mcp.py

EXPOSE 8922

CMD ["python3", "/app/browser_mcp.py"]
