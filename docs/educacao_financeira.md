# Educação financeira: como o Hausto atende a Resolução Conjunta nº 8

A premissa (a) do case pede que o agente siga a **Resolução Conjunta nº 8, de 21/12/2023** (CMN e Banco Central),
que trata das medidas de educação financeira das instituições. O texto usado aqui é o oficial, publicado pelo
Banco Central. A norma foi alterada pela Resolução Conjunta nº 20/2026, que acrescenta orientação a clientes com
dívidas em atraso de forma recorrente. Este mapeamento cobre o texto original. O Hausto já trata parte desse caso
quando falta dinheiro (linha do art. 2º, § 1º, III), mas não foi desenhado a partir da alteração.

Cada linha diz o que o artigo pede, onde o agente cumpre e como isso é verificado (testes unitários, que rodam na CI
em toda PR, e roteiros de eval com o Gemini). `tests/test_normas.py` falha se este documento citar um arquivo ou
roteiro que não existe.

## Art. 2º: medidas de educação financeira para pessoas físicas

O Hausto atende clientes pessoa física, no momento da fatura do cartão, com os números do próprio cliente.

| Trecho | O que pede | Como o Hausto cumpre | Onde | Como verificamos |
|---|---|---|---|---|
| Art. 2º, § 1º, I | Organização e planejamento do orçamento pessoal e familiar | Plano até a próxima renda: quanto pagar da fatura, quanto guardar e limite diário do dia a dia, com aceite do cliente e aviso quando ele sai do plano. Gráficos de para onde vai o dinheiro e das datas até a renda. | `app/plano.py`, `app/agente/planejador.py`, `app/visuais.py` | Evals `pl01`, `pl02`, `vi01`, `vi02`; testes `tests/test_plano.py`, `tests/test_planejador.py` |
| Art. 2º, § 1º, II | Formação de poupança e resiliência financeira | A reserva que o cliente quer manter entra nas restrições de todo cálculo. No plano, a reserva pedida é o mínimo a guardar e a sobra do mês vira reserva (`reserva_com_sobra`), em vez de liberar o limite máximo. | `app/calculos.py`, `app/plano.py`, `app/agente/prompt_planejador.md` | Evals `d04`, `d05`, `pl03`; teste `tests/test_plano.py` |
| Art. 2º, § 1º, III | Prevenção ao inadimplemento e ao superendividamento | Alerta antes do vencimento. Custo de cada forma de pagar em reais, com os juros do cartão e os da conta negativa. Essenciais preservados até a renda. Quando falta dinheiro: como pagar menos juros, onde cortar no dia a dia e parcelamento com o banco. Nunca recomenda crédito. | `app/calculos.py`, `app/painel.py`, `app/agente/prompt.md`, `app/guardrails.py` | Evals `i01`, `i02`, `c03`, `sf01`, `sf02`, `pl04`, `x02`, `g08`; testes `tests/test_sem_folga.py`, `tests/test_seguranca.py` |

## Art. 3º: política baseada em ética, responsabilidade, transparência e diligência

| Trecho | O que pede | Como o Hausto cumpre | Onde | Como verificamos |
|---|---|---|---|---|
| Art. 3º, caput | Ética, responsabilidade, transparência e diligência | Todo número vem das regras ou das tools e é validado antes de chegar ao cliente. Taxas e mínimo aparecem como premissas ilustrativas. A decisão é do cliente, com confirmação explícita. Sem produto e sem promessa. Senha, cartão e CPF são apagados antes do LLM. | `app/agente/grafo.py`, `app/guardrails.py`, `app/agente/juiz.py` | Métrica `juiz_fidelidade` em todos os roteiros; evals `c01`, `c02`, `g05`, `x01`; teste `tests/test_seguranca.py` |
| Art. 3º, I | Valor para o cliente: ações úteis e relevantes | Explica rotativo, IOF e custo com os números da fatura do próprio cliente, no momento em que ele precisa decidir. | `app/agente/prompt.md`, `app/visuais.py` | Evals `e02`, `e03`, `l01`, `l02`, `h01` |
| Art. 3º, II | Amplo alcance: acesso para o universo de clientes | Disponível a qualquer cliente pessoa física do app, pelo chat e pelos avisos da tela inicial, sem pré-requisito. Outros canais (WhatsApp, agência) ficam fora do escopo do MVP. | `app/agente/aberturas.py`, `app/painel.py` | Evals rodam com clientes reais de perfis diferentes (`e01` a `e04`) |
| Art. 3º, III | Adequação e personalização: linguagem, canal e momento adequados ao perfil | Tom por persona (quem paga tudo recebe só a confirmação; quem rola sempre recebe acolhimento sem culpa). Linguagem simples, sem jargão. Acolhimento para quem está aflito. Avisos no momento certo: antes do vencimento, quando falta folga, em imprevistos e no desvio do plano. Checagem simples de compreensão ("Ficou claro?"), com nova explicação se o cliente pedir. | `app/agente/prompt.md`, `app/agente/texto.py`, `app/agente/grafo.py` | Evals `e01`, `e04`, `fp02`, `g07`, `l03`; teste `tests/test_compreensao.py` |
| Art. 3º, § 1º, I | Considerar as fases do relacionamento | Avisos por momento: fatura perto de vencer, sem folga, imprevisto e acompanhamento do plano aceito. | `app/painel.py`, `app/agente/aberturas.py` | Testes `tests/test_visuais.py`, `tests/test_plano.py` |
| Art. 3º, § 1º, II | Compatível com o modelo de negócio e a complexidade do produto | Escopo fechado na fatura do cartão pessoa física. O agente não paga, não agenda e não contrata nada. | `app/agente/prompt.md` | Evals `x01`, `x02`, `g03` |

## Art. 4º: acompanhamento e controle da política

| Trecho | O que pede | Como o Hausto cumpre | Onde | Como verificamos |
|---|---|---|---|---|
| Art. 4º, I | Implementação das disposições | Testes automáticos em toda PR (backend e front) e evals com o Gemini sobre o comportamento esperado. | `.github/workflows/ci.yml`, `evals/roteiros.yaml` | CI da PR |
| Art. 4º, II | Monitoramento do cumprimento e da efetividade, com métricas e indicadores | Indicador de compreensão: quantos disseram que entenderam na primeira explicação e depois de reexplicar (`GET /v1/indicadores/compreensao`, métrica 3 da ficha). Evals com cinco métricas (estado, trajetória de tools, trajetória, fidelidade e experiência). Logs estruturados por evento (`[AGENTE][COMPREENSAO]`, `[AGENTE][GUARDRAIL]`, `[AGENTE][VALIDACAO]`) e traces no LangSmith. | `app/agente/grafo.py`, `evals/roteiros.yaml` | Teste `tests/test_compreensao.py`; eval `l03` |
| Art. 4º, III | Identificação e correção de ineficiências | Em tempo real: número sem fonte ou resposta inadequada gera uma reescrita e, se persistir, a resposta segura; juiz nos casos delicados. Na evolução: as falhas das evals e as respostas "Explica de novo" apontam onde a explicação não funcionou. | `app/agente/grafo.py`, `app/agente/juiz.py` | Testes `tests/test_seguranca.py`, `tests/test_agente.py` |

## Fora do agente

Os demais dispositivos são institucionais e não cabem num agente: política unificada por conglomerado (art. 3º,
§§ 2º e 3º), diretor responsável (art. 5º) e atribuições do Banco Central (arts. 6º e 7º).
