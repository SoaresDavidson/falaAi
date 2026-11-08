# Fala Aí

Newsletters do Gmail viram um podcast diário em pt-BR. O app roda em Docker no servidor
(`jessejamesserver`) com sidecar Tailscale; Ollama e Kokoro rodam no laptop (100.74.37.102).

## Setup, em ordem

1. Laptop: copie `deploy/laptop/ollama-override.conf` para
   `/etc/systemd/system/ollama.service.d/override.conf`, rode
   `sudo systemctl daemon-reload && sudo systemctl restart ollama` e
   `OLLAMA_HOST=100.74.37.102:11434 ollama pull qwen3:30b-a3b-instruct-2507`.
2. Laptop: instale `espeak-ng`, rode `uv sync --extra tts` e ative a unit:
   `cp deploy/laptop/falaai-tts.service ~/.config/systemd/user/ && systemctl --user enable --now falaai-tts`.
3. Laptop: rode `falaai auth` e copie o token para `data/gmail-token.json` no servidor.
4. Servidor: `cp .env.example .env` e preencha `TS_AUTHKEY` e `FALAAI_FEED_BASE_URL`.
5. Servidor: `docker compose up -d --build`.
6. Prometheus e Grafana: acrescente `deploy/prometheus/scrape-falaai.yaml` ao `prometheus.yml` e copie
   `deploy/grafana/falaai-alertas.yaml` para o provisioning de alerting do Grafana; reinicie ambos.
7. Celular: assine o feed em `http://falaai.<tailnet>.ts.net:8000/feed.xml` (com a tailnet ativa).
8. Uso: `curl -X POST http://falaai:8000/jobs`.
