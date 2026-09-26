"""Qual LLM usar, pelo ambiente (MODO_LLM).

- vertex    Gemini no Vertex AI com ADC (Cloud Run / gcloud auth application-default login)
- gemini    Gemini API com GOOGLE_API_KEY
- simulado  sem LLM: extração por regras e resposta montada direto das tools (custo zero)
"""

from __future__ import annotations

import os
from typing import Any

from app.agente.extracao import Extrator, extrair_por_regras, extrator_llm


def modo_llm() -> str:
    if modo := os.getenv("MODO_LLM"):
        return modo
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "vertex" if os.getenv("GOOGLE_CLOUD_PROJECT") else "simulado"


def modelo_chat() -> Any | None:
    if modo_llm() == "simulado":
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI

    modelo = os.getenv("MODELO", "gemini-3.8-flash")
    # WhatsApp não espera 70 s: poucas tentativas curtas; se falhar, o grafo responde sem LLM.
    limites = {"timeout": float(os.getenv("LLM_TIMEOUT_S", "20")), "max_retries": int(os.getenv("LLM_MAX_RETRIES", "1"))}
    if modo_llm() == "vertex":
        return ChatGoogleGenerativeAI(
            model=modelo,
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
            **limites,
        )
    return ChatGoogleGenerativeAI(model=modelo, **limites)


def extrator(modelo: Any | None) -> Extrator:
    return extrator_llm(modelo) if modelo is not None else extrair_por_regras
