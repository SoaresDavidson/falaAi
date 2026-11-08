"""Estágio de extração: Newsletter -> Itens."""

from falaai.domain import Item, Newsletter
from falaai.ports import Llm
from falaai.roteiro import prompts

SCHEMA = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "descricao": {"type": "string"},
                    "link": {"type": ["string", "null"]},
                },
                "required": ["titulo", "descricao", "link"],
            },
        }
    },
    "required": ["itens"],
}


def extrair_itens(llm: Llm, newsletter: Newsletter) -> list[Item]:
    usuario = (
        f"Remetente: {newsletter.remetente}\nAssunto: {newsletter.assunto}\n\n{newsletter.texto}"
    )
    resposta = llm.json(prompts.EXTRACAO, usuario, SCHEMA)
    itens = []
    for bruto in resposta.get("itens", []):
        titulo = (bruto.get("titulo") or "").strip()
        if not titulo:
            continue
        itens.append(
            Item(
                titulo=titulo,
                descricao=(bruto.get("descricao") or "").strip(),
                link=bruto.get("link") or None,
                fonte=newsletter.remetente,
                newsletter_id=newsletter.gmail_id,
            )
        )
    return itens
