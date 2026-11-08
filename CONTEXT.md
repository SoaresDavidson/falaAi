# Fala Aí

Serviço pessoal que lê newsletters do Gmail e as converte em um podcast diário em pt-BR, conversado por dois apresentadores e gerado inteiramente em máquinas próprias, sem serviços de IA externos.

## Language

### Entrada

**Newsletter**:
Um email recebido de um remetente assinado, identificado pela label `newsletter` do Gmail. Está pendente até virar parte de um Episódio publicado; depois disso, é arquivada.
_Avoid_: Email, mensagem

**Item**:
Uma notícia extraída de uma Newsletter, com título, descrição, link e fonte.
_Avoid_: Notícia, artigo, entrada

**Tópico**:
Um agrupamento de Itens sobre o mesmo assunto, vindos de uma ou mais Newsletters. É a unidade de pauta do Roteiro.
_Avoid_: Assunto, tema, cluster

### Roteiro e Episódio

**Roteiro**:
Diálogo narrável em pt-BR entre os Apresentadores, composto por uma sequência de Falas e organizado em Tópicos, com abertura e fechamento.
_Avoid_: Resumo, script, texto

**Fala**:
Um trecho contínuo do Roteiro dito por um único Apresentador.
_Avoid_: Linha, turno, fala do script

**Apresentador**:
Uma das duas personas fixas do Podcast: Dora, que conduz a pauta, e Alex, que comenta e contextualiza.
_Avoid_: Host, narrador, locutor, voz

**Episódio**:
Um arquivo de áudio gerado a partir de um Roteiro, com título, data e Shownotes. Tem duração limitada; Tópicos que não cabem ficam só nas Shownotes.
_Avoid_: Podcast, áudio, mp3

**Shownotes**:
A lista de todos os Itens (com links) considerados para um Episódio, incluindo os que não entraram no áudio.
_Avoid_: Descrição, notas, fontes

**Podcast**:
O conjunto de todos os Episódios, exposto como feed RSS privado.
_Avoid_: Feed, canal, show

### Execução

**Job**:
Uma execução completa, disparada manualmente, que transforma as Newsletters pendentes recentes, ou as de um dia escolhido, em um Episódio publicado. Termina em sucesso, erro ou sem Episódio (nenhuma Newsletter pendente). Um Job interrompido retoma do último estágio concluído.
_Avoid_: Run, execução, pipeline, tarefa
