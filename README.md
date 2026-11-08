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

### 4. Servidor: código e token

O deploy fica no repositório de configuração do servidor, em
`~/my-servers-config/docker/apps/falaai`: compose, sidecar Tailscale com HTTPS (`ts-serve.json`) e
as variáveis `FALAAI_*`. `TS_AUTHKEY`, `TS_DOMAIN` e `CONFIG_HOST_PATH` vêm do `.env` compartilhado
de lá. Este repositório só fornece o código, de onde a imagem é construída.

```bash
# No servidor
git clone git@github.com:SoaresDavidson/falaAi.git ~/falaAi
mkdir -p /DATA/AppData/media-stack/falaai
```

```bash
# No laptop: envia o token e apaga a cópia local
scp ~/gmail-token.json jessejamesserver:/DATA/AppData/media-stack/falaai/gmail-token.json
ssh jessejamesserver 'chmod 600 /DATA/AppData/media-stack/falaai/gmail-token.json'
rm ~/gmail-token.json
```

### 5. Servidor: subir o app

```bash
cd ~/my-servers-config/docker/apps/falaai
docker compose up -d --build
docker compose ps

# Deve responder com as métricas falaai_*.
docker exec falaai_tailscale wget -qO- http://127.0.0.1:8000/metrics | grep falaai_job_em_andamento
```

Depois de um `git pull` aqui, rode de novo o `docker compose up -d --build` lá.

O scrape do Prometheus (job `falaai`) e os alertas do Grafana (pasta "Fala Ai") também estão no
`my-servers-config`. O alvo aparece em http://192.168.100.35:9091/targets e as regras em
http://192.168.100.35:3001, em Alerting.

### 6. Celular

Com a Tailscale ligada, assine no app de podcast:

```text
https://falaai.<tailnet>.ts.net/feed.xml
```

## Uso

Com o laptop ligado (Ollama e `falaai-tts` no ar):

```bash
# Gera o Episódio de hoje, ou retoma o último Job que falhou.
curl -X POST https://falaai.<tailnet>.ts.net/jobs

# Acompanha o Job.
curl -s https://falaai.<tailnet>.ts.net/jobs/ultimo

# Descarta a retomada e começa um Job novo.
curl -X POST "https://falaai.<tailnet>.ts.net/jobs?novo=1"

# Job novo só com as Newsletters recebidas num dia (fuso FALAAI_FUSO).
curl -X POST "https://falaai.<tailnet>.ts.net/jobs?dia=2026-11-06"
```

Sem `?dia=`, o Job só pega Newsletters dos últimos `FALAAI_GMAIL_JANELA_DIAS` dias (padrão 2; as
variáveis ficam no compose do `my-servers-config`).
As mais antigas continuam pendentes no Gmail e não são arquivadas; use `?dia=` para gerar um
Episódio de um dia específico, ou `FALAAI_GMAIL_JANELA_DIAS=0` para pegar todas.

Os logs estão no Dozzle ou em `docker logs -f falaai`.

## Desenvolvimento

```bash
uv sync --extra tts
uv run pytest
uv run ruff check src tests
```
