"""Planejador: subagente do plano. O orquestrador (`conversa`) só chama `montar_plano`; o planejador simula,
propõe e devolve a proposta estruturada. Histórico isolado, prompt próprio e limite de chamadas."""

from langchain_core.messages import AIMessage
from pydantic import Field
from test_agente import ModeloFalso, ctx_padrao, novo_grafo

from app import calculos, plano
from app.agente import conversar, planejador
from app.agente.ferramentas import FERRAMENTAS
from app.agente.texto import brl


class ModeloGravador(ModeloFalso):
    """Guarda as mensagens de cada chamada: mostra o que o orquestrador e o planejador enxergaram."""

    vistas: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.vistas.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def pelo_planejador(*chamadas, resumo=None, final="Montei um plano até a renda.", extra=None,
                    pedido="monta um plano", antes=()):
    """Orquestrador chama montar_plano; o planejador faz `chamadas` (e resume, se não propôs); o orquestrador responde.

    `propor_plano` encerra o planejador: depois dela não há chamada de resumo.
    """
    return ModeloGravador(responses=[
        *antes,
        AIMessage("", tool_calls=[{"name": "montar_plano", "args": {"pedido": pedido}, "id": "m1"}, *(extra or [])]),
        *(AIMessage("", tool_calls=[{"name": nome, "args": args, "id": f"p{i}"}]) for i, (nome, args) in enumerate(chamadas)),
        *([AIMessage(resumo)] if resumo is not None else []),
        AIMessage(final),
    ])


def _plano_que_cabe(ctx):
    c = calculos.comparar_opcoes(ctx)
    s = plano.simular(ctx, c, c["valor_fatura"])
    return c, s, {"pagamento_fatura": c["valor_fatura"], "reserva": 0, "limite_diario": s["limite_maximo"]}


def _texto(mensagens):
    return "\n".join(m.text for m in mensagens)


def test_orquestrador_nao_tem_as_tools_internas_do_plano():
    assert {"simular_plano", "propor_plano"}.isdisjoint(f.name for f in FERRAMENTAS)


def test_orquestrador_delega_o_plano_e_so_ve_montar_plano():
    ctx = ctx_padrao()
    c, s, args = _plano_que_cabe(ctx)
    modelo = pelo_planejador(("simular_plano", {"pagamento_fatura": c["valor_fatura"]}), ("propor_plano", args))
    grafo, store = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.tools == ["montar_plano"]
    assert t.pendente_confirmacao["tipo"] == "plano" and t.pendente_confirmacao["limite_diario"] == s["limite_maximo"]
    assert store.get(("planos", ctx.id_usuario), "ativo") is None  # só vale depois do sim


def test_planejador_recebe_so_o_pedido_sem_o_historico():
    ctx = ctx_padrao()
    _, _, args = _plano_que_cabe(ctx)
    conversa_antes = AIMessage("Sua fatura fecha semana que vem. Quer se organizar até a renda?")
    modelo = pelo_planejador(("propor_plano", args), pedido="plano para se organizar até a renda", antes=[conversa_antes])
    grafo, _ = novo_grafo(modelo)
    conversar(grafo, ctx, "s1", "oi")
    conversar(grafo, ctx, "s1", "quero um plano pra me organizar")
    orquestrador, planejador_viu = modelo.vistas[1], modelo.vistas[2]
    assert conversa_antes.text in _texto(orquestrador) and conversa_antes.text not in _texto(planejador_viu)
    assert [type(m).__name__ for m in planejador_viu] == ["SystemMessage", "HumanMessage"]
    assert "plano para se organizar até a renda" in planejador_viu[1].text
    assert "quero um plano pra me organizar" in planejador_viu[1].text  # a fala do cliente vai junto do pedido
    # Cada um com o seu prompt: as regras do plano não pesam no prompt do orquestrador.
    assert "simular_plano" in planejador_viu[0].text and "simular_plano" not in orquestrador[0].text


def test_numeros_da_proposta_servem_de_fonte_para_a_resposta():
    ctx = ctx_padrao()
    c, s, args = _plano_que_cabe(ctx)
    final = f"Proposta: pagar {brl(c['valor_fatura'])} e gastar até {brl(s['limite_maximo'])} por dia no dia a dia."
    grafo, _ = novo_grafo(pelo_planejador(("propor_plano", args), final=final))
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.numeros_sem_fonte == [] and t.reescritas == 0 and brl(s["limite_maximo"]) in t.resposta


def test_planejador_termina_ao_propor_sem_chamada_de_resumo():
    ctx = ctx_padrao()
    _, _, args = _plano_que_cabe(ctx)
    modelo = pelo_planejador(("propor_plano", args))
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.pendente_confirmacao and len(modelo.vistas) == 3  # orquestrador, planejador (propõe), orquestrador


def test_planejador_ja_recebe_as_simulacoes_iniciais_e_elas_viram_fonte():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    normal = plano.normal_diario(ctx)
    inicial = plano.simular(ctx, c, c["valor_fatura"], limite_diario=normal)
    args = {"pagamento_fatura": c["valor_fatura"], "reserva": inicial["reserva_com_sobra"], "limite_diario": normal}
    final = f"Proposta: gastar até {brl(normal)} por dia e guardar {brl(inicial['reserva_com_sobra'])}."
    modelo = pelo_planejador(("propor_plano", args), final=final)
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert str(inicial["reserva_com_sobra"]) in modelo.vistas[1][1].text  # veio no pedido, sem o planejador simular
    assert t.numeros_sem_fonte == [] and t.reescritas == 0
    assert t.pendente_confirmacao["reserva"] == inicial["reserva_com_sobra"]


def test_numero_inventado_no_resumo_do_planejador_nao_vira_fonte():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    inventado = "Dá para guardar R$ 4.321,99 a mais."
    modelo = pelo_planejador(("simular_plano", {"pagamento_fatura": c["valor_fatura"]}), resumo=inventado,
                             final=f"Ainda não fechei o plano. {inventado}")
    modelo.responses.append(AIMessage("Ainda não fechei o plano. Quer ajustar o pagamento ou o limite?"))
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.reescritas == 1 and "4.321,99" not in t.resposta


def test_plano_proposto_sobrevive_a_reescrita_da_resposta():
    ctx = ctx_padrao()
    _, s, args = _plano_que_cabe(ctx)
    modelo = pelo_planejador(("propor_plano", args), final="Montei um plano e sobram R$ 4.321,99.")
    modelo.responses.append(AIMessage("Montei um plano até a renda, com um limite diário para o dia a dia."))
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.reescritas == 1 and "4.321,99" not in t.resposta
    assert t.pendente_confirmacao and t.pendente_confirmacao["limite_diario"] == s["limite_maximo"]


def test_plano_que_nao_cabe_nao_vira_proposta():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    args = {"pagamento_fatura": c["valor_fatura"], "reserva": 0, "limite_diario": 10_000_000}
    modelo = pelo_planejador(("propor_plano", args), final="Esse limite não fecha. Quer tentar um valor menor?")
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "quero gastar 10 milhões por dia")
    assert t.pendente_confirmacao is None and t.modo_resposta == "llm"


def test_planejador_em_loop_para_no_limite_e_o_turno_segue():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    simular = {"name": "simular_plano", "args": {"pagamento_fatura": c["valor_fatura"]}}
    modelo = ModeloGravador(responses=[
        AIMessage("", tool_calls=[{"name": "montar_plano", "args": {"pedido": "monta um plano"}, "id": "m1"}]),
        *(AIMessage("", tool_calls=[{**simular, "id": f"s{i}"}]) for i in range(planejador.LIMITE_CHAMADAS)),
        AIMessage("Não consegui fechar um plano agora. Quer tentar com outro valor?"),
    ])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.pendente_confirmacao is None and t.modo_resposta == "llm" and t.tools == ["montar_plano"]
    assert len(modelo.vistas) == planejador.LIMITE_CHAMADAS + 2  # o planejador não passou do limite


def test_sem_plano_possivel_nem_chama_o_planejador():
    ctx = ctx_padrao("insuficiente")
    c = calculos.comparar_opcoes(ctx)
    assert not plano.simular(ctx, c, c["opcoes"]["minimo"]["valor_pago"])["cabe"]  # nem o mínimo fecha
    modelo = ModeloGravador(responses=[
        AIMessage("", tool_calls=[{"name": "montar_plano", "args": {"pedido": "monta um plano"}, "id": "m1"}]),
        AIMessage("Nem pagando o mínimo dá para fechar um plano agora. Quer ver o que dá para ajustar?"),
    ])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert len(modelo.vistas) == 2 and t.pendente_confirmacao is None  # orquestrador antes e depois; planejador não
    assert t.numeros_sem_fonte == []
