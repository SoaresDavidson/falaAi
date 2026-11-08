# Fala Aí

Newsletters do Gmail viram um podcast diário em pt-BR. O app roda em Docker no servidor
(`jessejamesserver`) com sidecar Tailscale; Ollama e Kokoro rodam no laptop (`100.74.37.102`).
Arquitetura e decisões: `CONTEXT.md` e `docs/adr/`.

## Setup

Rode os blocos na ordem. Cada um diz em qual máquina rodar. Os comandos assumem o repositório em
`~/Projetos/falaAi` no laptop e em `~/falaAi` no servidor.

### 1. Laptop: Ollama na tailnet

```bash
cd ~/Projetos/falaAi
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo cp deploy/laptop/ollama-override.conf /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama

# A partir de agora o CLI local também precisa do OLLAMA_HOST.
export OLLAMA_HOST=100.74.37.102:11434
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M

# Deve listar o modelo.
curl -s http://100.74.37.102:11434/api/tags | grep qwen3
```

### 2. Laptop: serviço de TTS (Kokoro)

```bash
cd ~/Projetos/falaAi
sudo pacman -S --needed espeak-ng
uv sync --extra tts

mkdir -p ~/.config/systemd/user
cp deploy/laptop/falaai-tts.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now falaai-tts

# Deve responder {"carregado": false}.
curl -s http://100.74.37.102:8880/health
```

Para o serviço subir no boot mesmo sem login: `sudo loginctl enable-linger $USER`.

### 3. Laptop: autorizar o Gmail

No Google Cloud Console, no projeto que você já tem em produção:

1. Ative a Gmail API.
2. Adicione o escopo `https://www.googleapis.com/auth/gmail.modify` à tela de consentimento.
3. Baixe as credenciais OAuth do tipo "App para computador" como `~/Downloads/client_secret.json`.

Depois:

```bash
cd ~/Projetos/falaAi
uv run falaai auth --client-secret ~/Downloads/client_secret.json --saida ~/gmail-token.json
```

O comando abre o navegador. Autorize com a conta que recebe as newsletters.

### 4. Servidor: código, dados e token

```bash
# No servidor
git clone https://github.com/SoaresDavidson/falaAi.git ~/falaAi
cd ~/falaAi
mkdir -p data
sudo chown 1000:1000 data
```

```bash
# No laptop: envia o token e apaga a cópia local
scp ~/gmail-token.json jessejamesserver:falaAi/data/gmail-token.json
ssh jessejamesserver 'chmod 600 ~/falaAi/data/gmail-token.json'
rm ~/gmail-token.json
```

### 5. Servidor: configuração

Gere uma auth key em https://login.tailscale.com/admin/settings/keys. Use uma key reutilizável
ou com expiração longa, com a tag que você usa nos outros serviços.

```bash
# No servidor
cd ~/falaAi
TAILNET=$(tailscale status --json | grep -m1 -oP '"MagicDNSSuffix":\s*"\K[^.]+')   # ex.: tail1234
cp .env.example .env
sed -i "s|^TS_AUTHKEY=.*|TS_AUTHKEY=tskey-auth-COLE_AQUI|" .env
sed -i "s|<tailnet>|$TAILNET|" .env
chmod 600 .env
grep -E "TS_AUTHKEY|FEED_BASE_URL" .env
```

### 6. Servidor: subir o app

```bash
cd ~/falaAi
docker compose up -d --build
docker compose ps

# Deve responder com as métricas falaai_*.
docker exec falaai_tailscale wget -qO- http://localhost:8000/metrics | grep falaai_job_em_andamento
```

### 7. Servidor: Prometheus e alertas no Discord

```bash
cd ~/falaAi
CONF=/home/davi/my-servers-config/docker/server/prometheus

# Insere o job de scrape logo abaixo de "scrape_configs:", com a indentação de 2 espaços dos outros jobs.
cp $CONF/prometheus.yml $CONF/prometheus.yml.bak
grep -v '^#' deploy/prometheus/scrape-falaai.yaml | sed 's/^/  /' > /tmp/scrape-falaai.yaml
sed -i '/^scrape_configs:/r /tmp/scrape-falaai.yaml' $CONF/prometheus.yml
docker run --rm -v $CONF/prometheus.yml:/p.yml --entrypoint promtool prom/prometheus check config /p.yml
docker restart prometheus

# Alertas (Job com erro, Job travado há mais de 2 h, app fora do ar).
cp deploy/grafana/falaai-alertas.yaml $CONF/grafana/provisioning/alerting/
docker restart grafana
```

Em http://192.168.100.35:9091/targets, o alvo `falaai` deve aparecer como `UP`. As regras ficam
no Grafana (http://192.168.100.35:3001), em Alerting, na pasta "Fala Ai".

### 8. Celular

Com a Tailscale ligada, assine no app de podcast:

```text
http://falaai.<tailnet>.ts.net:8000/feed.xml
```

O endereço exato está em `grep FEED_BASE_URL ~/falaAi/.env`, no servidor.

## Uso

Com o laptop ligado (Ollama e `falaai-tts` no ar):

```bash
# Gera o Episódio de hoje, ou retoma o último Job que falhou.
curl -X POST http://falaai:8000/jobs

# Acompanha o Job.
curl -s http://falaai:8000/jobs/ultimo

# Descarta a retomada e começa um Job novo.
curl -X POST "http://falaai:8000/jobs?novo=1"
```

Os logs estão no Dozzle ou em `docker logs -f falaai`.

## Desenvolvimento

```bash
uv sync --extra tts
uv run pytest
uv run ruff check src tests
```
