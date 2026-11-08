# Roteiro gerado em estágios com checkpoint

Em vez de uma única chamada de LLM com todas as Newsletters, o Roteiro é gerado em três estágios, cada um persistido no SQLite: (1) uma chamada por Newsletter extrai Itens em JSON estruturado; (2) uma chamada agrupa os Itens em Tópicos, ordena e corta no teto de duração do Episódio; (3) uma chamada por Tópico gera suas Falas, além da abertura e do fechamento. As chamadas ficam pequenas para o contexto de um modelo local. Como o laptop pode dormir ou desconectar no meio do Job (ADR-0001), um Job interrompido retoma do último estágio concluído em vez de refazer horas de inferência.

## Consequences

- As Newsletters só são marcadas como processadas no Gmail depois de o Episódio ser publicado (ADR-0004). Uma falha em qualquer estágio deixa as Newsletters pendentes.
- O app usa o escopo `gmail.modify`, e não o `gmail.readonly`, exclusivamente para poder marcá-las como processadas.
