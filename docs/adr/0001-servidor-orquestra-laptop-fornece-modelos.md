# Servidor orquestra; laptop fornece LLM e TTS por HTTP

O servidor (`jessejamesserver`, i7-4980HQ, 15 GB de RAM, sem GPU utilizável, ~8 GB livres com 53 containers e sem swap) não roda modelos bons: um LLM de ~8B em CPU é lento e mediano, e qualquer coisa maior arrisca acionar o OOM killer sobre outros serviços. O laptop (RTX 4070 com 8 GB de VRAM e 30 GB de RAM) roda bem o `qwen3:30b-a3b-instruct-2507-q4_K_M` e o Kokoro. Decidimos que o servidor é o único dono do estado e da orquestração (app Python em Docker, SQLite, feed, métricas), e chama o Ollama e um serviço Kokoro nativos do laptop pela Tailscale, ambos com bind só no IP Tailscale.

## Considered Options

- **LLM em CPU no servidor**: rejeitado pela qualidade do Roteiro e pelo risco de memória.
- **Pipeline inteiro como CLI no laptop, enviando o resultado ao servidor**: rejeitado porque divide o estado entre duas máquinas e dificulta métricas e alertas.
- **Entregar o Roteiro ao laptop por uma pasta do Nextcloud**: rejeitado porque a sincronização não sinaliza arquivo completo, não devolve erros ao servidor e exige um daemon vigiando a pasta.
- **Agendar o Job no servidor, esperando ou fazendo polling até o laptop ficar online**: rejeitado. Quem dispara é o próprio laptop (timer systemd diário com `Persistent=true`, que roda assim que ele volta a ficar ligado), ou uma pessoa com `POST /jobs`.

## Consequences

- Sem o laptop online não há Episódio. Por isso o agendamento fica no laptop: um timer perdido dispara no próximo boot ou resume, e um Job que falhou é retomado pelo disparo seguinte.
- O LLM e o TTS disputam os 8 GB de VRAM. Ao fim do último estágio de LLM, o servidor descarrega o modelo explicitamente (`keep_alive: 0`) antes de pedir áudio, e o serviço de TTS carrega o Kokoro sob demanda e o libera quando fica ocioso. Sem isso, o TTS falha com `CUDA out of memory` enquanto o LLM continua carregado pelo `keep_alive` padrão.
