# Como executar o experimento

Todo o ambiente é gerenciado por [uv](https://docs.astral.sh/uv/). O interpretador
está fixado em `.python-version` e as versões exatas das dependências em `uv.lock`,
ambos versionados — não é preciso instalar Python manualmente nem resolver pacotes.

## 1. Preparar o ambiente

```bash
uv sync                     # cria .venv com as versões travadas em uv.lock
cp .env.example .env        # preencher GOOGLE_API_KEYS
```

As chaves são obtidas em <https://aistudio.google.com/apikey> e vão em
`GOOGLE_API_KEYS`, separadas por vírgula (`GOOGLE_API_KEY`, no singular, continua
aceita para uma chave só). O arquivo `.env` está no `.gitignore` e nunca é gravado nos
resultados: o manifesto registra apenas **quantas** chaves a rodada usou, nunca quais.

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

O modo escolhe as condições comparadas (ver [strategies.md](strategies.md) e
[experimental-decisions.md](experimental-decisions.md) §14):

| `--mode` | Condição |
| --- | --- |
| `sampling` | apenas a amostragem independente (best-of-N) |
| `critic` | apenas a revisão guiada pelo Agente Crítico (vê o gabarito, prosa livre) |
| `critic-no-oracle` | crítico que nunca vê o gabarito do teste |
| `critic-cegis` | crítico que vê o gabarito e devolve um contraexemplo estruturado |
| `both` | `sampling` + `critic`, sobre as mesmas tarefas (padrão) |
| `all` | as quatro condições, sobre as mesmas tarefas |

As três condições de crítico alternam Gerador↔Crítico do mesmo jeito e custam 2 chamadas
por ciclo de revisão — **o orçamento deve ser ímpar** vale para as três, pelo mesmo
motivo que já valia para `critic` (ver seção 5 abaixo).

Opções adicionais: `--split`, `--seed`, `--budget`, `--generator-model`,
`--critic-model`, `--sampling-temperature`, `--rpm-total`, `--rpm`, `--workers`,
`--run-id`, `--fresh`, `--quiet`.
Cada uma sobrepõe o valor correspondente do `.env` apenas naquela execução.

### Exemplos

```bash
# uma tarefa, as duas condições, para inspecionar o comportamento
uv run arc-exp run --task 007bbfb7 --mode both

# rodada oficial: 100 tarefas de evaluation, orçamento ímpar de 7 chamadas
uv run arc-exp run --sample 100 --mode both --budget 7

# só a revisão guiada, em uma tarefa que a amostragem errou
uv run arc-exp run --task 0520fde7 --mode critic
```

Para ver o experimento por dentro — a sequência real de mensagens trocadas com o
modelo nas duas condições, extraída da rodada oficial — veja
[exemplo-execucao.md](exemplo-execucao.md).

## 4. Leitura do relatório

```
Task      sampling   critic
--------  --------  -------
0520fde7   ✗ 7c/7i   ✓ 7c/4i
```

`7c/7i` = 7 chamadas à API e 7 iterações de código. Em `critic` metade das chamadas
vai para o Crítico, então o mesmo orçamento rende menos programas — é exatamente essa
troca que o experimento mede.

A tabela de condições traz acurácia (acerto no par de teste), taxa de consistência
com os pares de treino, média de chamadas e de iterações, eventos do filtro
anti-vazamento e erros de API. O bloco final traz a comparação pareada com o
p-valor exato de McNemar.

## 5. Free tier e limites de taxa

O experimento roda no free tier do Google AI Studio. Prefira o modelo `flash` mais
recente que sua chave alcançar — hoje `gemini-3.7-flash`. Duas armadilhas já
verificadas na prática:

- os modelos `gemini-2.5-*` respondem **404** para chaves criadas recentemente
  ("no longer available to new users");
- um projeto com **billing habilitado não tem free tier**: sem créditos, toda chamada
  volta como 429 "prepayment credits are depleted". Para usar o free tier, gere a chave
  em um projeto sem billing.

Para descobrir o que sua chave alcança, liste os modelos com
`client.models.list()` (ver `google-genai`). Evite os aliases `gemini-flash-latest` e
`gemini-pro-latest` na rodada oficial: eles mudam sozinhos e quebram a reprodutibilidade.

O free tier impõe limites de naturezas diferentes, que exigem tratamentos
diferentes.

**Taxa agregada (`RPM_TOTAL`).** É o número que importa, e foi medido: com uma chave
sozinha, 20 chamadas seguidas a 30 req/min passam sem uma recusa; com o pool inteiro
acima de ~30 req/min **somados**, os 429 aparecem em qualquer chave, de qualquer
projeto. A taxa de recusa acompanha o total de requisições, não o que cada chave faz.
Por isso `RPM_TOTAL` limita o pool como um só, e enquanto ele for maior que zero é o
único limitador em vigor.

**Cuidado com `RPM`, que é por chave.** Ele continua disponível (com `RPM_TOTAL=0`),
mas por ser por chave o teto agregado cresce com o número de chaves: 12 chaves a
`RPM=30` autorizam **360 req/min**. Foi exatamente assim que uma rodada de 270 tarefas
morreu depois de uma única tarefa concluída — ~135 requisições em 40 segundos, 38% de
falha, todas as 12 chaves fora de circulação.

**Recusas transitórias são o regime normal, não a exceção.** Medindo o free tier,
~4% das chamadas voltam como um `429 RESOURCE_EXHAUSTED` pelado — sem `quotaId`, sem
`retryDelay`, sem cabeçalho de cota — ou como `503` de modelo sobrecarregado, e a mesma
chave responde normalmente segundos depois. Não é a sua cota acabando; é o serviço
descartando carga. O pool trata isso pondo a chave de molho por um tempo crescente
(30 s, dobrando até 5 min) e devolvendo-a; só depois de seis pausas seguidas sem
resposta ela é dada como perdida para aquele modelo. Quando *todas* estão de molho, a
rodada espera a primeira voltar em vez de terminar.

**Requisições por dia (RPD).** Só um 429 que **diga** `per day`, ou que fale em billing,
é tratado como definitivo — esses não dá para esperar dentro da execução. A chave sai de
circulação para aquele modelo (a cota é por modelo, então ela ainda pode servir outro) e
as chamadas seguintes vão para as demais. Só quando todas esgotam a rodada para, com
código de saída 2, preservando tudo que já foi gravado. Repita o mesmo comando quando as
cotas resetarem: a retomada pula as tarefas concluídas.

Erros permanentes (chave inválida, requisição malformada) falham de imediato, sem
consumir tentativas e sem queimar as outras chaves — uma requisição malformada falharia
igual em todas.

### Várias chaves

As chamadas vão sempre para a chave menos usada entre as disponíveis, de modo que as
cotas drenam parelho em vez de esgotar uma de cada vez. Com `RPM_TOTAL` em vigor, todas
partilham **um** limitador: o teto é do pool, e acrescentar chaves não o aumenta.

Por padrão, a rodada usa **um worker por chave** (`--workers N` sobrepõe). Como o
limitador agregado é que dita o ritmo, mais workers só mantêm mais tarefas na fila —
não aceleram a rodada. Ao final, o console mostra e `keys.json` grava quantas chamadas
cada chave atendeu, quantas pausas ela tomou (`quarantines`) e quais modelos ficaram
definitivamente fora (`exhausted`).

Três advertências, todas verificadas na prática:

- a cota é contada **por projeto**, não por chave: várias chaves do mesmo projeto
  compartilham a mesma cota e não somam capacidade nenhuma;
- **mesmo com projetos distintos, as chaves não somam taxa.** Foi medido: uma chave
  sozinha sustenta 30 req/min limpos, mas o pool inteiro começa a levar 429 por volta de
  30 req/min **somados**, independentemente de como as requisições se distribuem entre as
  chaves. Mais chaves compram mais cota diária, não mais taxa;
- **simultaneidade não é o gatilho, taxa é.** A mesma taxa agregada passa igual com 12
  requisições em voo ou com 3. Se aparecerem 429 em excesso, baixe `--rpm-total`, não
  `--workers`.

### Dimensionamento

O custo de uma rodada em requisições é:

```
tarefas × condições × orçamento por tarefa
```

A rodada oficial (100 tarefas, duas condições, `BUDGET_CALLS=7`) custa **1.400
requisições** no teto. O tempo, porém, não sai do número de chaves: sai de `RPM_TOTAL`.
A `arc-exp run` imprime o piso antes de começar.

| Configuração | Requisições | Piso a 25 req/min |
| --- | --- | --- |
| 100 tarefas, budget 7, `--mode both` | 1.400 | ~56 min |
| 50 tarefas, budget 7, `--mode both` | 700 | ~28 min |
| 270 tarefas, budget 7, `--mode all` (3 críticos) | 5.670 | ~3,8 h |
| 10 tarefas, budget 7, `--mode both` | 140 | ~6 min |

O número é um teto: tarefas resolvidas cedo gastam menos que o orçamento — nas rodadas
já feitas, as condições de crítico gastaram ~5,5 chamadas das 7. Reduzir o orçamento por
tarefa é preferível a reduzir a amostra: o poder do teste pareado depende do número de
tarefas (ver decisão 9 em `experimental-decisions.md`), e um orçamento menor apenas
aperta a competição de forma igual para as duas condições.

**O orçamento deve ser ímpar.** `critic` alterna Gerador→Crítico→Gerador; com um
orçamento par, a última chamada só poderia ser uma crítica sem revisão subsequente, e
o laço corretamente a recusa — a condição gastaria uma chamada a menos que a
amostragem, sem proveito.

### Verificação de diversidade

A amostragem só é um baseline honesto se as N amostras forem de fato diferentes entre
si. Antes da rodada oficial, vale medir isso com o modelo que será usado:

```bash
uv run arc-exp run --sample 10 --mode sampling --budget 7 --run-id diversity-check
```

Depois, conte quantos programas distintos cada tarefa produziu:

```bash
uv run python -c "
import json, pathlib
for line in pathlib.Path('results/runs/diversity-check/sampling.jsonl').read_text().splitlines():
    r = json.loads(line)
    codes = {i['code'] for i in r['iterations'] if i['code']}
    print(r['task_id'], len(codes), 'distinto(s) de', len(r['iterations']))
"
```

Se a mediana ficar em 1 ou 2, a temperatura não está entregando diversidade e precisa
subir (`--sampling-temperature`) antes da rodada oficial — caso contrário o best-of-N
vira uma única tentativa repetida, e a comparação perde o sentido.

## 6. Resultados e retomada

Cada rodada grava em `results/runs/<run-id>/`:

- `manifest.json` — commit do Git, versão do Python, configuração sem segredos,
  hash dos prompts de sistema e lista de tarefas;
- `sampling.jsonl` e `critic.jsonl` — uma linha por tarefa, com todas as iterações,
  regras, códigos, feedbacks do Crítico (versão filtrada e bruta) e contabilidade do
  orçamento.

O `run-id` é derivado da configuração (`evaluation-n100-seed20260814-b7`), então
repetir o comando **retoma** a rodada e pula as tarefas já registradas. Para
recomeçar do zero, use `--fresh`.

Os `.jsonl` brutos não são versionados (ver `.gitignore`); o manifesto e os
agregados usados na nota técnica devem ser commitados manualmente.

## 7. Testes e tipagem

```bash
uv run pytest      # suíte completa, sem rede
uv run mypy        # tipagem estrita em src/ e tests/
```
