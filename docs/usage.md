# Como executar o experimento

Todo o ambiente é gerenciado por [uv](https://docs.astral.sh/uv/). O interpretador
está fixado em `.python-version` e as versões exatas das dependências em `uv.lock`,
ambos versionados — não é preciso instalar Python manualmente nem resolver pacotes.

## 1. Preparar o ambiente

```bash
uv sync                     # cria .venv com as versões travadas em uv.lock
cp .env.example .env        # preencher GOOGLE_API_KEY
```

A chave é obtida em <https://aistudio.google.com/apikey>. O arquivo `.env` está no
`.gitignore` e nunca é gravado nos resultados: o manifesto de cada rodada registra a
configuração sem a chave.

## 2. Verificar a instalação sem gastar API

```bash
uv run arc-exp run --sample 4 --mode both --budget 3 --dry-run
```

`--dry-run` substitui o modelo por uma resposta fixa e percorre o pipeline inteiro
(prompt, execução em sandbox, orçamento, registro, relatório). Serve para conferir a
instalação; os números produzidos não têm valor experimental.

## 3. Comandos

| Comando | O que faz |
| --- | --- |
| `arc-exp run --task <id>` | roda uma tarefa específica |
| `arc-exp run --sample <n>` | sorteia `n` tarefas com a seed configurada |
| `arc-exp report --run-id <id>` | re-exibe o relatório de uma rodada concluída |
| `arc-exp tasks --sample <n>` | lista quais tarefas a seed seleciona, sem executar |

O modo escolhe as condições comparadas:

| `--mode` | Condição |
| --- | --- |
| `single` | apenas o baseline (gerador + self-debugging) |
| `feedback` | apenas a intervenção (gerador + Agente Crítico) |
| `both` | as duas, sobre as mesmas tarefas (padrão) |

Opções adicionais: `--split`, `--seed`, `--budget`, `--generator-model`,
`--critic-model`, `--run-id`, `--fresh`, `--quiet`. Cada uma sobrepõe o valor
correspondente do `.env` apenas naquela execução.

### Exemplos

```bash
# uma tarefa, as duas condições, para inspecionar o comportamento
uv run arc-exp run --task 007bbfb7 --mode both

# rodada oficial: 100 tarefas de evaluation, orçamento de 12 chamadas por tarefa
uv run arc-exp run --sample 100 --mode both --budget 12

# só a intervenção, em uma tarefa que o baseline errou
uv run arc-exp run --task 0520fde7 --mode feedback
```

## 4. Leitura do relatório

```
Task      baseline  intervention
--------  --------  ------------
0520fde7   ✗ 12c/12i     ✓ 8c/4i
```

`12c/12i` = 12 chamadas à API e 12 iterações de código. Na intervenção metade das
chamadas vai para o Crítico, então o mesmo orçamento rende menos iterações — é
exatamente essa troca que o experimento mede.

A tabela de condições traz acurácia (acerto no par de teste), taxa de consistência
com os pares de treino, média de chamadas e de iterações, eventos do filtro
anti-vazamento e erros de API. O bloco final traz a comparação pareada com o
p-valor exato de McNemar.

## 5. Resultados e retomada

Cada rodada grava em `results/runs/<run-id>/`:

- `manifest.json` — commit do Git, versão do Python, configuração sem segredos,
  hash dos prompts de sistema e lista de tarefas;
- `baseline.jsonl` e `intervention.jsonl` — uma linha por tarefa, com todas as
  iterações, regras, códigos, feedbacks do Crítico (versão filtrada e bruta) e
  contabilidade do orçamento.

O `run-id` é derivado da configuração (`evaluation-n100-seed20260814-b12`), então
repetir o comando **retoma** a rodada e pula as tarefas já registradas. Para
recomeçar do zero, use `--fresh`.

Os `.jsonl` brutos não são versionados (ver `.gitignore`); o manifesto e os
agregados usados na nota técnica devem ser commitados manualmente.

## 6. Testes e tipagem

```bash
uv run pytest      # suíte completa, sem rede
uv run mypy        # tipagem estrita em src/ e tests/
```
