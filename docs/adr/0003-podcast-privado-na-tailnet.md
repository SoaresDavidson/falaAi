# Podcast privado na tailnet, servido pelo próprio app

O Podcast contém o conteúdo das newsletters pessoais do usuário, então o feed RSS e os mp3 ficam acessíveis só pela tailnet, servidos pelo próprio app Python (o `FileResponse` do Starlette atende requisições Range, de que os apps de podcast precisam), sem reverse proxy. Rejeitamos o Tailscale Funnel e o storage público (R2) porque a única proteção seria uma URL secreta. O custo é que o celular precisa estar com a Tailscale ativa para atualizar o feed.

## Consequences

- O app também fica acessível, sem autenticação, para os containers da rede Docker `medianet` do servidor, onde o sidecar Tailscale entra para que o Prometheus consiga coletar `/metrics`. Esses containers conseguem ler o feed e disparar `POST /jobs`. Isso é aceito porque a `medianet` só tem serviços do próprio usuário. Se isso mudar, a saída é expor só `/metrics` na interface Docker.
