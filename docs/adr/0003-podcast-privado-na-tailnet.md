# Podcast privado na tailnet, servido pelo próprio app

O Podcast contém o conteúdo das newsletters pessoais do usuário, então o feed RSS e os mp3 ficam acessíveis só pela tailnet, servidos pelo próprio app Python (o `FileResponse` do Starlette atende requisições Range, de que os apps de podcast precisam), sem reverse proxy. Rejeitamos o Tailscale Funnel e o storage público (R2) porque a única proteção seria uma URL secreta. O custo é que o celular precisa estar com a Tailscale ativa para atualizar o feed.
