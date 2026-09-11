FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY core ./core
COPY orchestrator ./orchestrator
COPY workers ./workers
COPY registry ./registry

CMD ["uv", "run", "python", "-m", "workers.hardcoded_worker"]
