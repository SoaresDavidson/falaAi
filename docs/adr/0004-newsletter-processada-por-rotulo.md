# Newsletter processada marcada por rótulo, não pela Caixa de entrada

Uma Newsletter está pendente quando tem o rótulo `newsletter` e não tem o rótulo `falaai-processada`. Depois que o Episódio é publicado, o app aplica `falaai-processada` às Newsletters dele (e as tira da Caixa de entrada, se estiverem lá). Antes, pendente era estar na Caixa de entrada, e processar era arquivar. Mas o filtro do Gmail que aplica `newsletter` também pula a Caixa de entrada, e assim nenhuma Newsletter chegava a ficar pendente. Rejeitamos mudar o filtro para não encher a Caixa de entrada com newsletters que o usuário só quer ouvir.

## Consequences

- O app cria o rótulo `falaai-processada` na primeira publicação, se ele não existir. O escopo `gmail.modify` já cobre isso.
- Newsletters antigas com o rótulo `newsletter` contam como pendentes. A janela padrão (`FALAAI_GMAIL_JANELA_DIAS=2`) evita pegar o histórico inteiro; com a janela em 0, aplique `falaai-processada` à mão no que não deve virar Episódio.
- Remover o rótulo `falaai-processada` de uma Newsletter a devolve à fila.
