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
    from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory

    modelo = os.getenv("MODELO", "gemini-3.8-flash")
    # WhatsApp não espera 70 s: poucas tentativas curtas; se falhar, o grafo responde sem LLM.
    limites = {"timeout": float(os.getenv("LLM_TIMEOUT_S", "20")), "max_retries": int(os.getenv("LLM_MAX_RETRIES", "1"))}
    # Thinking do Gemini 3.x vem ligado: ~600 tokens de raciocínio por chamada (6,6 s -> 2,2 s com "low").
    # As contas estão nas regras e tools; LLM_THINKING="" volta ao padrão do modelo.
    if thinking := os.getenv("LLM_THINKING", "low"):
        limites["thinking_level"] = thinking
    # Filtro do próprio Gemini só no nível alto: pega o grave sem barrar cliente irritado ou aflito.
    # Resposta bloqueada chega vazia e o grafo usa a resposta fixa.
    limites["safety_settings"] = {categoria: HarmBlockThreshold.BLOCK_ONLY_HIGH for categoria in (
        HarmCategory.HARM_CATEGORY_HARASSMENT, HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT)}
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
