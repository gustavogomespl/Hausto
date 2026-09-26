# Hausto

Protótipo de gestão financeira para pessoa física: compreender a intenção do
cliente, comparar o pagamento da fatura com o caixa e os compromissos até a
próxima renda e explicar as consequências. Implementado em **Python 3.12,
FastAPI, LangGraph/LangChain**, com integrações previstas para Gemini e BigQuery.

Esta entrega implementa atualização de contexto, encaminhamento, revisão
programada e registros de execução. **Os quatro agentes Mesh planejados ainda
não estão implementados como especialistas independentes.** O fluxo atual tem
extração de informações, um agente conversacional com ferramentas e etapas
programadas. Nenhuma ferramenta executa pagamentos.

## Executar localmente no Windows

Pré-requisitos: Git, Python 3.12 e `uv` disponível no terminal. Execute na raiz do
repositório, usando PowerShell:

```powershell
uv sync --frozen --no-install-project
$env:MODO_LLM = "simulado"
$env:FONTE_DADOS = "mock"
uv run --no-sync uvicorn main:app --reload --host 127.0.0.1 --port 8080
```

Se `uv` já estiver instalado apenas dentro da `.venv`, use
`.\.venv\Scripts\uv.exe` no lugar de `uv` nos comandos.

Abra a interface em <http://127.0.0.1:8080> e a documentação da API em
<http://127.0.0.1:8080/docs>. O endpoint `/saude` informa os modos ativos.
Encerre com `Ctrl+C`. Reiniciar ou recarregar o servidor apaga as sessões e
intenções registradas em memória.

`simulado` usa extração por regras e respostas com texto fixo, sem chamadas ao
Gemini. `mock` lê o CSV versionado, sem consultar BigQuery. A instalação inicial
das dependências pode precisar de rede; a execução dessa combinação não exige
credenciais Google. Os comandos acima não carregam `.env` automaticamente.

O fixture contém **90 transações inventadas de três clientes**, entre julho e
dezembro de 2025. Não é a base oficial do desafio, nem evidência de impacto.
Sua referência padrão é **18/12/2025**, independente da data do computador.
Detalhes e origem estão em [data/mock/README.md](data/mock/README.md).

## Testar

Em outro terminal, na mesma pasta:

```powershell
$env:MODO_LLM = "simulado"
$env:FONTE_DADOS = "mock"
uv run --no-sync pytest -q
```

A suíte usa dados locais e modelos falsos. Cobre cálculos, atualização do
contexto, pendências, confirmação, revisão, isolamento de sessões e rotas da
API; não valida chamadas reais ao Gemini ou ao BigQuery. Para regenerar
exatamente o fixture fictício:

```powershell
uv run --no-sync python scripts/gerar_mock_sintetico.py
```

O cenário Bruno, com capacidade de R$ 3.400 caindo para R$ 2.900 após uma despesa
de R$ 500, é um caso sintético em `tests/test_contexto_financeiro.py`. Ele não
corresponde a um dos três clientes do CSV.

## Conferir a jornada

Na interface, selecione `demo-001` e mantenha a mesma conversa. Pela API, use
`POST /v1/chat` com `id_usuario: "demo-001"`, `data_ref: "2025-12-18"` e a
`mensagem`. Reutilize o `sessao_id` devolvido em todos os turnos seguintes.

| Mensagem | Comportamento esperado |
| --- | --- |
| `Minha fatura é R$ 1.000 e quero guardar R$ 100` | Atualiza os fatos e apresenta a simulação. |
| `Tenho uma nova despesa de R$ 500` | Pede a data e suspende a comparação enquanto falta informação. |
| `28/12/2025` | Completa a despesa pendente, muda a versão e recalcula. |
| `Quero pagar o mínimo` | Solicita confirmação de uma intenção vinculada à proposta e à versão atuais. |
| `Sim, mas tenho uma nova despesa de R$ 200 em 29/12/2025` | Descarta a confirmação pendente, atualiza o contexto e recalcula. |

Para registrar uma intenção, faça uma nova escolha depois do recálculo e
responda apenas `sim` à confirmação. O registro é uma intenção na simulação;
nenhum débito é realizado. Mensagens com ressalvas não confirmam a proposta
antiga. O extrator por regras reconhece um conjunto limitado de formulações;
para datas, informe dia, mês e ano completos.

## O que foi construído

| Componente | Responsabilidade |
| --- | --- |
| `app/agente/extracao.py` | Extrai fatos e escolhas; diferencia despesas de saldo e mantém informações ausentes. |
| `app/agente/contexto.py` | Centraliza fatos, origens, despesas, pendências e `versao_contexto`. Alterações invalidam comparações e escolhas anteriores. |
| `app/agente/contexto_financeiro.py` | Adapta o contexto confirmado aos cálculos, preservando o extrato original e informando as premissas. |
| `app/agente/grafo.py` | Encaminha para esclarecimento, cálculo, revisão, conversa ou confirmação. Separa falha técnica de insuficiência de caixa. |
| `app/agente/revisao.py` e `app/guardrails.py` | Verificam versão, consistência básica, restrições e números da resposta. São verificações programadas, não um segundo parecer financeiro independente. |

Cada resposta da API inclui `turno_id`, `versao_contexto`, `eventos`, `revisao`,
`pendencias` e `modo_resposta`. Eventos também são emitidos no log com o marcador
`evento_hausto`, nome da etapa, status, versão e horário. `tools_chamadas` registra
ferramentas chamadas pelo subagente conversacional; no modo simulado essa lista
pode ficar vazia, e o cálculo programado aparece em `eventos`.

## Integrar a frente Conta e Compromissos

O ponto de integração desta entrega é:

```python
comparar_contexto(ctx: ContextoCliente, dados: dict, despesas: list[dict]) -> dict
```

- `ctx` vem da aplicação, nunca de um identificador escolhido pelo modelo.
- `dados` pode conter `valor_fatura`, `saldo_atual`, `reserva_desejada`,
  `essenciais_informados` e `proxima_renda` em formato `AAAA-MM-DD`.
- `essenciais_informados` substitui a estimativa base entre o vencimento e a
  próxima renda. Não é uma despesa adicional.
- `despesas` contém itens já confirmados como adicionais, com `id`, `descricao`,
  `valor` e `data`. O grafo filtra os itens confirmados e bloqueia pendências.
- Na janela `data_ref <= data < proxima_renda`, despesas até o vencimento
  reduzem o caixa; despesas posteriores aumentam os compromissos. Cada item
  entra uma vez. A mesma identificação com dados conflitantes gera erro.
- O retorno inclui opções, capacidade, metadados em `contexto_financeiro` e
  aviso de simulação. Erros retornam `erro` e `motivo`; não devem virar uma
  conclusão de insuficiência. O grafo acrescenta a versão usada no cálculo.

Ao substituir ou separar as ferramentas financeiras, mantenha esse contrato,
a origem dos dados, os erros explícitos e a ligação com a versão do contexto.
Os especialistas devem devolver resultados; a atualização dos fatos permanece
centralizada. Antes de ampliar o Mesh, valide o recálculo e a confirmação de
ponta a ponta.

## Conectar ao Google

O código oferece `MODO_LLM=vertex` para Gemini no Vertex AI com credenciais ADC,
ou `MODO_LLM=gemini` com `GOOGLE_API_KEY`. Para dados, `FONTE_DADOS=bigquery` usa
`BQ_TABELA` e as permissões do projeto. `.env.example` documenta as variáveis;
o arquivo aponta para serviços externos, portanto não é necessário copiá-lo
para a demonstração local acima.

Antes da integração real, a equipe precisa conferir modelo disponível, região,
projeto, permissões, credenciais e eventuais custos. Não coloque chaves ou
arquivos de credenciais no Git. **Gemini/Vertex e BigQuery reais não foram
validados nesta entrega.**

## Limites atuais

- A API é de demonstração e não possui autenticação. O isolamento por cliente
  e sessão no grafo não substitui controle de acesso. Use dados fictícios e
  execução local até implementar autenticação e autorização.
- Sessões, decisões e cache ficam no processo. Não há persistência entre
  reinícios nem coordenação entre várias instâncias.
- Taxas, mínimo de 15% e demais condições são fixos do protótipo. Não são
  condições contratuais verificadas; capacidade de caixa não é recomendação
  de pagamento. A revisão não comprova adequação financeira ou conformidade.
- O cálculo atual exige próxima renda posterior ao vencimento. Despesas no
  dia do vencimento reduzem o caixa por cautela; o dia da próxima renda está
  fora da janela. Outras sequências exigem ampliar o modelo temporal.
- Projeções históricas e o pequeno fixture permitem testar comportamento, mas
  não demonstram precisão, redução de inadimplência ou benefício ao cliente.
