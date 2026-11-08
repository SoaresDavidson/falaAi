FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY src ./src
# Sem o extra `tts`: o Kokoro roda no laptop.
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 falaai && mkdir /data && chown falaai /data
USER falaai
VOLUME /data
EXPOSE 8000

CMD ["falaai", "serve", "--host", "0.0.0.0", "--port", "8000"]
