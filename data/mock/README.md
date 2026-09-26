# Extrato sintético para desenvolvimento local

`transacoes.csv` foi criado do zero pelo gerador
`scripts/gerar_mock_sintetico.py`. Não contém dados de clientes, exportações do
BigQuery, identificadores reais ou linhas copiadas de outros arquivos. Pode ser
versionado com o código para permitir a execução dos testes sem serviços externos.

São **90 transações fictícias de três clientes**, de julho a dezembro de 2025.
Os identificadores, valores, descrições e datas são inventados. A repetição mensal
é intencional: torna as projeções determinísticas fáceis de conferir. Os saldos
partem de um saldo anterior ao período e são atualizados em centavos a cada linha.
Não há múltiplas transações na mesma data para o mesmo cliente.

| Cliente | Saldo anterior a julho | Cenário na referência padrão de 18/12/2025 |
| --- | ---: | --- |
| `demo-001` | R$ 4.200 | Caixa projetado de R$ 5.700 e essenciais de R$ 600; cenário com recursos disponíveis. |
| `demo-002` | R$ 2.000 | Caixa projetado de R$ 3.300 e essenciais de R$ 600; segundo cliente para isolamento e confirmação. |
| `demo-003` | R$ 0 | Caixa projetado de R$ 1.100 e essenciais de R$ 1.000; capacidade de R$ 100 antes de reserva, insuficiente para o mínimo estimado pelo protótipo atual. |

As faturas históricas são registradas como pagamentos parciais no dia 25; a renda
ocorre no dia 5. Mercado e combustível ficam após o vencimento, exercitando a
janela de essenciais até a próxima renda. Em **28/11/2025**, a função atual de
estimativa não considera novembro fechado para a fatura de dezembro: o cenário
permite testar a pergunta pelo valor da fatura.

Esses resultados descrevem a lógica atual do protótipo, **não validam taxas,
mínimo contratual, recomendação financeira ou precisão de previsão**. O arquivo
não é amostra estatística, base de calibração, reprodução dos clientes Bruno e
Carla do pitch nem evidência de impacto. As constantes de estimativa e de juros
existentes no código têm origem independente deste fixture.

## Regenerar e testar sem Google Cloud

Na raiz do repositório, com o ambiente Python do projeto preparado:

```powershell
.venv\Scripts\python.exe scripts/gerar_mock_sintetico.py
$env:MODO_LLM = "simulado"
$env:FONTE_DADOS = "mock"
.venv\Scripts\python.exe -m pytest
```

O gerador usa somente a biblioteca padrão, não acessa a rede e não lê credenciais.
Reexecutá-lo produz os mesmos bytes. Para inspecionar uma cópia sem substituir o
fixture, use `--destino caminho/alternativo.csv`.

O script antigo `scripts/gerar_mock.py` tem outro propósito: extrair registros de
um arquivo recebido como entrada. Ele não foi usado para produzir este fixture.
Para manter a origem sintética deste arquivo versionado, regenere-o pelo script
`gerar_mock_sintetico.py`.
