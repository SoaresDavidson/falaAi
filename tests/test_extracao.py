from falaai.roteiro.extracao import extrair_itens
from tests.fakes import FakeLlm, newsletter


def test_extrai_e_descarta_sem_titulo():
    n = newsletter("n9")
    llm = FakeLlm(
        [
            {
                "itens": [
                    {"titulo": "A", "descricao": "a", "link": "https://a"},
                    {"titulo": "", "descricao": "b", "link": None},
                    {"titulo": "C", "descricao": "c", "link": None},
                ]
            }
        ]
    )
    itens = extrair_itens(llm, n)
    assert [i.titulo for i in itens] == ["A", "C"]
    assert all(i.fonte == n.remetente and i.newsletter_id == n.gmail_id for i in itens)
    assert itens[1].link is None


def test_itens_nulo_vira_vazio():
    assert extrair_itens(FakeLlm([{"itens": None}]), newsletter()) == []
