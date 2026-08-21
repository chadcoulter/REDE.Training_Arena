FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8787 \
    ARENA_HOST=127.0.0.1 \
    ARENA_PORT=4000

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY adapter/package.json ./adapter/package.json
RUN cd adapter && npm install --omit=dev

COPY . .
RUN chmod +x /app/deployment/start-stack.sh

EXPOSE 4000 4001 8787

CMD ["/app/deployment/start-stack.sh"]
