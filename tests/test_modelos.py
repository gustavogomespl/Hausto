"""Configuração do Gemini: o thinking fica baixo por padrão (≈3x mais rápido, medido na Vertex)."""

import pytest

from app.agente.modelos import modelo_chat


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("MODO_LLM", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "chave-de-teste")  # nenhuma chamada é feita
    monkeypatch.delenv("LLM_THINKING", raising=False)


def test_thinking_baixo_por_padrao(gemini):
    assert modelo_chat().reasoning_effort == "low"


def test_thinking_configuravel_pelo_ambiente(gemini, monkeypatch):
    monkeypatch.setenv("LLM_THINKING", "high")
    assert modelo_chat().reasoning_effort == "high"


def test_thinking_vazio_volta_ao_padrao_do_modelo(gemini, monkeypatch):
    monkeypatch.setenv("LLM_THINKING", "")
    assert modelo_chat().reasoning_effort is None


def test_modo_simulado_nao_cria_modelo(monkeypatch):
    monkeypatch.setenv("MODO_LLM", "simulado")
    assert modelo_chat() is None


def test_filtro_de_seguranca_do_gemini_so_no_nivel_alto(gemini):
    from langchain_google_genai import HarmBlockThreshold, HarmCategory
    filtros = modelo_chat().safety_settings
    assert filtros[HarmCategory.HARM_CATEGORY_HARASSMENT] == HarmBlockThreshold.BLOCK_ONLY_HIGH
    assert set(filtros.values()) == {HarmBlockThreshold.BLOCK_ONLY_HIGH} and len(filtros) == 4
