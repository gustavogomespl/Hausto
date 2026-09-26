"""Entrada do LangGraph Studio (`langgraph.json`). O servidor do Studio traz checkpointer e store.

No Studio, preencha o contexto com {"id_usuario": "<id do mock>"} e mande uma mensagem.
"""

from app.agente.grafo import construir_grafo
from app.agente.modelos import extrator, modelo_chat

_modelo = modelo_chat()
grafo = construir_grafo(modelo=_modelo, extrator=extrator(_modelo))
