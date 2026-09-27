# Evals do agente de fatura

48 roteiros multiturno (`roteiros.yaml`), cada um rodado com um cliente real da base escolhido
pelo perfil (persona, caixa suficiente ou não, fatura estimável). Runner e painel: promptfoo.

## Rodar

```bash
evals/rodar.sh                                   # Vertex + BigQuery + juiz Gemini (precisa de gcloud auth application-default login)
EVALS_JUIZ=0 MODO_LLM=simulado FONTE_DADOS=mock evals/rodar.sh   # só checagens determinísticas, sem custo
evals/rodar.sh --filter-pattern "^d0"            # só um grupo de roteiros (pela descrição)
evals/painel.sh                                  # painel em http://localhost:15500
uv run --group evals pytest tests/test_evals.py  # testes do próprio harness
```

## O que cada caso avalia

| Métrica no painel | Como | Aprova quando |
|---|---|---|
| `estado` | Python, sem LLM | etapa, dados extraídos, recálculo, confirmação, números sem fonte, trechos, visuais, decisão e plano no fim batem com `espera` |
| `trajetoria_tools` | agentevals (`strict`, `unordered`, `subset`, `superset`) | as tools de cada turno batem com `espera.tools` |
| `juiz_trajetoria` | llm-rubric, Gemini 3.8 Flash | nota ≥ 0,8: tools certas, na hora certa, argumentos coerentes |
| `juiz_fidelidade` | llm-rubric | nota ≥ 0,8: números e afirmações vêm das tools, sem inventar |
| `juiz_experiencia` | llm-rubric | nota ≥ 0,8: clareza, tom da persona, pergunta final, sem produto |

O juiz lê a transcrição que o provider devolve: por turno, a mensagem, a rota de nós, as tools com
argumentos e saídas, os dados informados e a resposta.

## Plugar outro agente (ex.: multiagente)

1. Em `alvo.py`, crie uma classe com `rodar(ctx, mensagens) -> Execucao`, preenchendo um
   `TurnoTrace` por mensagem (etapa, tools com `nome/args/saida`, `pendente_confirmacao`, `dados`,
   `dados_mudaram`, `numeros_sem_fonte`, resposta). Registre em `ALVOS`.
2. Em `promptfooconfig.yaml`, acrescente um provider com `config: {alvo: <nome>}`.
3. `evals/rodar.sh` roda os dois; o painel mostra as colunas lado a lado.

Os roteiros esperam comportamento (etapa, dados, tools, números), não nomes de nós.
Se o novo agente usar outros nomes de etapa, mapeie para os de `roteiros.yaml` no adaptador.

## Lacunas conhecidas (devem falhar hoje)

- Nenhuma no momento. Roteiros que dependem de comportamento novo: c03 (escolha bloqueada).
