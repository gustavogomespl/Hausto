"""Testes do harness de evals (evals/): se o avaliador erra, a nota do agente mente."""

from collections import Counter

import pytest

pytest.importorskip("agentevals", reason="grupo evals: uv run --group evals pytest")
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app import calculos
from app.agente.extracao import extrair_por_regras
from app.dados import RepositorioMock
from evals import checagens, selecao
from evals.alvo import AlvoGrafo
from evals.gerar_testes import carregar_roteiros, criar_testes

REPO = RepositorioMock()


class ModeloFalso(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


# ------------------------------------------------------------------ roteiros


def test_sao_40_roteiros_com_ids_unicos_e_turnos():
    roteiros = carregar_roteiros()
    assert len(roteiros) == 40
    assert len({r["id"] for r in roteiros}) == 40
    assert all(r["turnos"] and all(t["mensagem"] for t in r["turnos"]) for r in roteiros)


def test_roteiros_cobrem_todas_as_categorias_do_design():
    cats = Counter(r["categoria"] for r in carregar_roteiros())
    assert cats == {
        "explicar_opcoes": 4, "hipotese_tool": 4, "dado_novo": 5, "insuficiencia": 3,
        "fatura_desconhecida": 2, "escolha_confirmacao": 4, "guardrail": 8, "falso_positivo": 4, "fora_escopo": 2,
        "outro_cliente": 1, "letramento": 2, "nova_despesa": 1,
    }


# ------------------------------------------------------------------ seleção de clientes


def test_selecao_respeita_o_perfil():
    ctx = selecao.escolher_cliente({"status": "insuficiente"}, "r1", REPO)
    assert calculos.comparar_opcoes(ctx)["status"] == "insuficiente"


def test_selecao_e_deterministica_por_roteiro():
    perfil = {"status": "ok"}
    a = selecao.escolher_cliente(perfil, "r1", REPO).id_usuario
    assert a == selecao.escolher_cliente(perfil, "r1", REPO).id_usuario


def test_selecao_por_fatura_nao_estimavel_usa_a_data_do_perfil():
    ctx = selecao.escolher_cliente({"fatura_pronta": False, "data_ref": "2025-11-28"}, "r1", REPO)
    assert not calculos.prever_fatura(ctx)["pronta"]


def test_selecao_sem_candidato_explica_o_perfil():
    with pytest.raises(LookupError, match="persona"):
        selecao.escolher_cliente({"persona": "P9"}, "r1", REPO)


# ------------------------------------------------------------------ alvo (grafo em processo)


def test_alvo_captura_nos_etapa_e_confirmacao_em_multiturno():
    ctx = selecao.escolher_cliente({"status": "ok"}, "r1", REPO)
    ex = AlvoGrafo(modelo=None).rodar(ctx, ["oi, e minha fatura?", "quero pagar o mínimo", "sim"])
    t1, t2, t3 = ex.turnos
    assert t1.etapa == "explicar_opcoes" and "calcular_opcoes" in t1.nos and "conversa" in t1.nos
    assert t2.pendente_confirmacao and t2.pendente_confirmacao["opcao"] == "minimo"
    assert t3.etapa == "decisao_registrada" and [d["opcao"] for d in ex.decisoes] == ["minimo"]


def test_alvo_captura_tool_com_argumentos_e_saida():
    ctx = selecao.escolher_cliente({"status": "ok"}, "r1", REPO)
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "simular_custo_rolagem", "args": {"valor_pago": 500}, "id": "c1"}]),
        AIMessage("Resposta sem números."),
    ])
    [t] = AlvoGrafo(modelo=modelo, extrator=extrair_por_regras).rodar(ctx, ["e se eu pagar 500?"]).turnos
    [tool] = t.tools
    assert tool["nome"] == "simular_custo_rolagem" and tool["args"] == {"valor_pago": 500}
    assert "custo_total" in tool["saida"]


# ------------------------------------------------------------------ checagens determinísticas


def _execucao(mensagens, espera, perfil=None):
    ctx = selecao.escolher_cliente(perfil or {"status": "ok"}, "r1", REPO)
    ex = AlvoGrafo(modelo=None).rodar(ctx, mensagens)
    roteiro = {"id": "r1", "turnos": [{"mensagem": m, "espera": e} for m, e in zip(mensagens, espera)]}
    return ex, roteiro


def test_checagem_passa_quando_o_turno_bate_com_o_esperado():
    ex, roteiro = _execucao(["minha fatura veio R$ 1.000,00"], [{"etapa": "explicar_opcoes", "dados": {"valor_fatura": 1000}}])
    r = checagens.avaliar_deterministico(roteiro, ex.para_dict())
    assert r["pass"], r["reason"]


def test_checagem_falha_e_diz_o_que_faltou():
    ex, roteiro = _execucao(["oi"], [{"etapa": "informar_deficit", "tools": {"modo": "superset", "lista": ["simular_custo_rolagem"]}}])
    estado = checagens.avaliar_deterministico(roteiro, ex.para_dict())
    trajetoria = checagens.avaliar_trajetoria(roteiro, ex.para_dict())
    assert not estado["pass"] and "etapa" in estado["reason"]
    assert not trajetoria["pass"] and "simular_custo_rolagem" in trajetoria["reason"]


def test_trajetoria_subset_vazio_proibe_qualquer_tool():
    ctx = selecao.escolher_cliente({"status": "ok"}, "r1", REPO)
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "prever_fatura", "args": {}, "id": "c1"}]),
        AIMessage("Resposta sem números."),
    ])
    ex = AlvoGrafo(modelo=modelo, extrator=extrair_por_regras).rodar(ctx, ["oi"])
    roteiro = {"id": "r1", "turnos": [{"mensagem": "oi", "espera": {"tools": {"modo": "subset", "lista": []}}}]}
    assert not checagens.avaliar_trajetoria(roteiro, ex.para_dict())["pass"]
    roteiro["turnos"][0]["espera"]["tools"]["lista"] = ["prever_fatura"]
    assert checagens.avaliar_trajetoria(roteiro, ex.para_dict())["pass"]


def test_checagem_de_decisao_registrada_no_fim():
    ex, roteiro = _execucao(["quero pagar o mínimo", "não"], [{"pendente": True}, {"etapa": "decisao_cancelada"}])
    roteiro["espera_final"] = {"decisao_registrada": False}
    assert checagens.avaliar_deterministico(roteiro, ex.para_dict())["pass"]
    roteiro["espera_final"] = {"decisao_registrada": True}
    assert not checagens.avaliar_deterministico(roteiro, ex.para_dict())["pass"]


def test_transcricao_para_o_juiz_mostra_rota_e_tools():
    ctx = selecao.escolher_cliente({"status": "ok"}, "r1", REPO)
    ex = AlvoGrafo(modelo=None).rodar(ctx, ["oi"])
    texto = ex.transcricao()
    assert "Cliente: oi" in texto and "rota:" in texto and "Agente:" in texto
    # o juiz de fidelidade precisa ver a fonte dos números que não vêm de tool
    assert "cálculo do turno" in texto and "valor_fatura" in texto


# ------------------------------------------------------------------ testes do promptfoo


def _qualquer_cliente(monkeypatch):
    """A estrutura dos casos não depende de quais perfis o mock tem."""
    from app.features import montar_contexto
    from evals import gerar_testes

    ctx = montar_contexto(REPO.transacoes(REPO.listar_clientes()[0]))
    monkeypatch.setattr(gerar_testes, "escolher_cliente", lambda perfil, semente: ctx)


def test_criar_testes_gera_40_casos_com_asserts(monkeypatch):
    _qualquer_cliente(monkeypatch)
    monkeypatch.setenv("EVALS_JUIZ", "1")
    testes = criar_testes()
    assert len(testes) == 40
    t = testes[0]
    assert t["vars"]["id_usuario"] and t["vars"]["roteiro"]
    tipos = [a["type"] for a in t["assert"]]
    assert tipos.count("python") == 2 and tipos.count("llm-rubric") == 3


def test_sem_juiz_so_ficam_as_checagens(monkeypatch):
    _qualquer_cliente(monkeypatch)
    monkeypatch.setenv("EVALS_JUIZ", "0")
    assert {a["type"] for t in criar_testes() for a in t["assert"]} == {"python"}


class ModeloForaDoAr(ModeloFalso):
    def _generate(self, *args, **kwargs):
        raise RuntimeError("504 DEADLINE_EXCEEDED")


def test_turno_com_llm_fora_do_ar_e_marcado_e_reprovado():
    ctx = selecao.escolher_cliente({"status": "ok"}, "r1", REPO)
    ex = AlvoGrafo(modelo=ModeloForaDoAr(responses=[]), extrator=extrair_por_regras).rodar(ctx, ["oi"])
    assert ex.turnos[0].resposta_fixa
    roteiro = {"id": "r1", "turnos": [{"mensagem": "oi", "espera": {"etapa": "explicar_opcoes"}}]}
    r = checagens.avaliar_deterministico(roteiro, ex.para_dict())
    assert not r["pass"] and "resposta fixa" in r["reason"]


def test_modo_simulado_nao_conta_resposta_fixa_como_falha():
    ex, roteiro = _execucao(["oi"], [{"etapa": "explicar_opcoes"}])
    assert not ex.turnos[0].resposta_fixa
    assert checagens.avaliar_deterministico(roteiro, ex.para_dict())["pass"]


def test_rubrica_de_experiencia_segue_o_formato_do_prompt():
    from evals.gerar_testes import RUBRICAS

    assert "- " in RUBRICAS["juiz_experiencia"] and "listas simples" in RUBRICAS["juiz_experiencia"]


def test_transcricao_mostra_a_escolha_calculada_na_confirmacao():
    ctx = selecao.escolher_cliente({"status": "ok"}, "r1", REPO)
    ex = AlvoGrafo(modelo=None).rodar(ctx, ["vou pagar R$ 500 agora"])
    assert ex.turnos[0].escolha["custo_total"] > 0
    assert "escolha calculada" in ex.transcricao()
