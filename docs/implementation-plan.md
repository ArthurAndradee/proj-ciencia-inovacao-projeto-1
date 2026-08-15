# Plano de implementação

Tradução do experimento descrito no `README.md` para código executável. O documento
descreve o que já está implementado, como as peças se encaixam e o que falta para a
rodada oficial.

## 1. O que o experimento compara

Duas condições resolvem as **mesmas** tarefas do ARC-AGI-1 sob o **mesmo** orçamento
de chamadas à API:

| Condição | Sigla no código | Ciclo |
| --- | --- | --- |
| Baseline (self-debugging) | `Condition.BASELINE` | Gerador propõe regra + código → executa nos pares de treino → recebe o resultado da execução → revisa |
| Intervenção (multi-agente) | `Condition.INTERVENTION` | Gerador propõe regra + código → executa → **Crítico** compara a regra declarada com o gabarito e devolve contradições → Gerador revisa |

A diferença é o canal de feedback. O Crítico gasta do mesmo orçamento do Gerador,
de modo que a intervenção troca iterações de código por densidade informacional —
a hipótese central do README.

## 2. Arquitetura

```
src/arc_experiment/
├── config.py        Config: lê .env, congela os parâmetros, exporta manifesto sem segredos
├── dataset.py       Task/Pair, carga dos JSON, amostragem determinística por seed
├── grids.py         serialização das grades e descrição textual das divergências
├── executor.py      extração do bloco de código e execução em subprocesso isolado
├── _sandbox_child.py  processo filho que roda transform() e devolve JSON
├── llm.py           Budget (orçamento compartilhado), GeminiClient, ScriptedClient
├── prompts.py       prompts de sistema e mensagens dos dois papéis
├── guards.py        filtro anti-vazamento aplicado ao feedback do Crítico
├── agents.py        Generator (com histórico) e Critic (sem memória entre rodadas)
├── runner.py        laço de solução de uma tarefa em cada condição
├── experiment.py    iteração sobre tarefas, manifesto, persistência JSONL retomável
├── metrics.py       sumários por condição e teste de McNemar exato pareado
├── report.py        renderização do relatório no console
└── cli.py           subcomandos run / report / tasks
```

Dependência em uma direção só: `cli → experiment → runner → agents → {llm, prompts,
guards, executor} → {grids, dataset, config}`. Cada módulo é testável isoladamente,
e a suíte inteira roda sem rede graças ao `ScriptedClient`.

## 3. Laço de solução (`runner.solve_task`)

1. O Gerador recebe os pares de treino e **apenas o input** do par de teste.
2. A resposta é dividida em regra (linguagem natural) e código.
3. O código roda em subprocesso isolado sobre os pares de treino.
4. Se reproduz todos os pares, a tarefa para com `train_consistent`.
5. Caso contrário:
   - baseline: monta feedback de execução e repete;
   - intervenção: se ainda cabem duas chamadas no orçamento, o Crítico é consultado,
     o feedback passa pelo filtro anti-vazamento e volta ao Gerador.
6. Ao fim, o melhor candidato pelos pares de treino é executado no par de teste. Esse
   resultado é a métrica de acerto.

As decisões de desenho por trás desse laço (o que o Crítico enxerga, por que o
gabarito do teste não é critério de parada, como o candidato final é escolhido) estão
em [experimental-decisions.md](experimental-decisions.md).

## 4. Registro e reprodutibilidade

- ambiente travado em `uv.lock` e `.python-version`;
- amostragem determinística: `seed` + `split` + `n` definem as tarefas;
- `manifest.json` grava commit do Git, versão do Python, configuração sem a chave e o
  hash SHA-256 dos prompts de sistema — se um prompt mudar, o hash denuncia;
- um JSONL por condição, com uma linha por tarefa contendo todas as iterações, o
  feedback do Crítico (filtrado e bruto) e a contabilidade do orçamento por papel;
- gravação incremental: uma rodada interrompida por rate limit continua de onde parou.

## 5. Estado atual

Implementado e coberto por testes: núcleo de dados, sandbox, orçamento, agentes,
filtro anti-vazamento, as duas condições, persistência retomável, métricas, relatório
e CLI. `uv run pytest` e `uv run mypy` passam sem rede.

Falta executar:

1. **Piloto** (~10 tarefas, `--mode both`, orçamento baixo) para calibrar prompts e
   verificar o formato das respostas do Gemini, sem valor experimental.
2. **Calibração do orçamento**: medir quantas iterações o baseline usa até estabilizar
   e fixar `BUDGET_CALLS` antes da rodada oficial. O valor precisa ser par, para que a
   intervenção consiga fechar seus ciclos gerador→crítico→gerador.
3. **Rodada oficial**: 100 tarefas de `evaluation`, seed registrada, as duas condições.
4. **Análise qualitativa**: ler os casos discordantes (`only_a` / `only_b`) e
   classificar em que situações a validação por oposição ajudou e em quais atrapalhou —
   é o que o README pede para a nota técnica.
5. **Nota técnica**: números da rodada, tabela de contingência, p-valor e a discussão
   dos casos, com as ameaças à validade já listadas nas decisões experimentais.

## 6. Extensões previstas, ainda não implementadas

- **Condição C (oráculo binário)**: baseline que apenas sabe se acertou o teste, sem
  feedback em linguagem natural. Separaria o efeito do *acesso ao gabarito* do efeito
  do *feedback estruturado*, hoje confundidos na intervenção.
- **Múltiplas repetições por tarefa** com temperatura > 0, para estimar variância.
- **Orçamento por tokens** como controle alternativo ao de chamadas.
