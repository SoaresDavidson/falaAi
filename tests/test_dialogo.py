from datetime import date

from falaai.domain import Fala, Pauta, Roteiro, Topico
from falaai.roteiro.dialogo import aplicar_teto, escrever_abertura, escrever_bloco
from tests.fakes import FakeLlm, item


def test_descarta_apresentador_invalido_e_vazio():
    llm = FakeLlm(
        [
            {
                "falas": [
                    {"apresentador": "dora", "texto": "Oi"},
                    {"apresentador": "bob", "texto": "Eita"},
                    {"apresentador": "alex", "texto": " "},
                ]
            }
        ]
    )
    t = Topico("T", (item("a"),), 100)
    assert escrever_bloco(llm, t) == (Fala("dora", "Oi"),)


def test_abertura_diz_data_em_ptbr():
    llm = FakeLlm([{"falas": [{"apresentador": "dora", "texto": "Oi"}]}])
    pauta = Pauta((Topico("Tema", (item("a"),), 100),), ())
    escrever_abertura(llm, pauta, date(2026, 11, 8))
    assert "8 de novembro de 2026" in llm.chamadas[0][0]
    assert "Tema" in llm.chamadas[0][1]


def _fala(n):
    return Fala("dora", " ".join(["p"] * n))


def test_aplicar_teto_remove_blocos_finais():
    itens = [item("a"), item("b"), item("c")]
    pauta = Pauta(tuple(Topico(f"T{i}", (itens[i],), 100) for i in range(3)), ())
    roteiro = Roteiro((_fala(10),), tuple((_fala(100),) for _ in range(3)), (_fala(10),))
    novo, nova_pauta = aplicar_teto(roteiro, pauta, 250)
    assert len(novo.blocos) == 2
    assert len(nova_pauta.topicos) == 2
    assert nova_pauta.fora_do_audio == (itens[2],)
