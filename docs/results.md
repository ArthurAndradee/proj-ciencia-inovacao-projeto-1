# Resultados

Registro das rodadas. A definição das condições está em [strategies.md](strategies.md);
as escolhas de desenho, em [experimental-decisions.md](experimental-decisions.md).

## Rodada oficial — análise interina, 100 tarefas

> **Estas 100 tarefas são a análise interina.** Em 20/08/2026, antes de executar a
> extensão, a amostra foi ampliada para 270 tarefas e a **análise principal do estudo
> passou a ser a das 270** — ver [decisão 12](experimental-decisions.md). Os números
> abaixo são descritivos e permanecem registrados para que a decisão de estender seja
> auditável, não como conclusão do experimento.

Concluída em 20/08/2026, `run-id` `official`, commit `82b0ebd`. Reproduzir com:

```bash
uv run arc-exp run --sample 100 --mode both --budget 7 --split evaluation \
  --run-id official
```

| Parâmetro | Valor |
| --- | --- |
| Modelo (ambos os papéis) | `gemini-3.5-flash-lite` |
| Split / seed | `evaluation` / 20260814 |
| Tarefas | 100 |
| `BUDGET_CALLS` | 7 (ímpar, ver decisão 6) |
| Temperatura | 0,8 (`sampling`) / 0,2 (`critic`) |
| Chaves | 6 em paralelo, ~165 chamadas cada |
| Tempo de execução | 13 minutos |

### Resultado

| Condição | Resolvidas | Acurácia | Consist. treino | Chamadas médias | Iterações médias |
| --- | --- | --- | --- | --- | --- |
| `sampling` | 25/100 | 25,0% | 27,0% | 5,78 | 5,78 |
| `critic` | 26/100 | 26,0% | 30,0% | 5,84 | 3,42 |

Comparação pareada:

| | |
| --- | --- |
| resolvidas por ambas | 17 |
| só `sampling` | 8 |
| só `critic` | 9 |
| por nenhuma | 66 |
| ganho líquido | +1 tarefa (+1,0 pp) |
| **McNemar exato** | **p = 1,0000** (17 pares discordantes) |

**A hipótese não se confirmou nesta análise interina.** Sob orçamento fixo de chamadas, a
revisão guiada por crítico-oráculo não superou a amostragem best-of-N. Nove tarefas contra oito é um empate:
com 17 discordantes, seriam necessários 13×4 para cruzar p < 0,05.

A taxa de discordância observada (17%) reproduziu exatamente a do piloto, que fundamentou
a escolha de 100 tarefas na decisão 9. O que não se materializou foi o desequilíbrio entre
as discordâncias — não o número delas.

O intervalo de confiança de 95% para a proporção de discordâncias a favor do crítico é
**[0,31, 0,74]**, largamente compatível com o empate (0,50).

### O crítico melhora o treino sem melhorar o teste

O resultado nulo na acurácia esconde um efeito de mecanismo:

| | consistentes com treino | dessas, acertaram o teste | overfit |
| --- | --- | --- | --- |
| `sampling` | 27 | 24 | 3 (11,1%) |
| `critic` | 30 | 23 | 7 (23,3%) |

O crítico **faz o que promete**: produziu mais programas consistentes com todo o conjunto
de treino (30 contra 27). Mas converteu essa consistência em acerto no teste com bem menos
eficiência — 77% contra 89%. A revisão guiada ajusta ao treino sem generalizar melhor, e é
por isso que +3 pp de consistência viraram apenas +1 pp de acurácia.

É a leitura mais interessante da rodada, e também a mais frágil: **nenhuma das duas
diferenças é significativa** com 100 tarefas.

| Hipótese | Teste | p |
| --- | --- | --- |
| crítico produz mais overfit (11% vs 23%) | Fisher exato | 0,3044 |
| crítico produz mais consistência de treino | McNemar pareado (8×5) | 0,5811 |

Ambas são **hipóteses exploratórias geradas por estes dados**, não hipóteses testadas.
Confirmá-las exige uma réplica em tarefas não utilizadas — ver a seção de extensão abaixo.

### Custo: as condições empataram em chamadas, não em tokens

| | chamadas | tokens | respostas truncadas |
| --- | --- | --- | --- |
| `sampling` | 578 | 3.131k | 5 |
| `critic` | 584 | 5.014k | 0 |

O orçamento controlado é o de **chamadas**, e nele as condições empataram como o desenho
exige. Em tokens, não: o crítico consumiu **60% a mais**, porque seu prompt carrega o
gabarito e o histórico acumulado. Uma avaliação de custo real, em vez de contagem de
requisições, mudaria a comparação — a limitação está declarada aqui de propósito.

### Extensão declarada — 270 tarefas

Declarada em 20/08/2026 **antes de executar**, com a justificativa completa e o custo
estatístico na [decisão 12](experimental-decisions.md). Em resumo:

- a análise principal passa a ser a das **270 tarefas**; estas 100 são interinas;
- o objetivo é **precisão, não significância** — o efeito observado exigiria ~13.300
  tarefas para ser detectável, o que nenhum N no split de 400 alcança. O que a extensão
  entrega é o intervalo de confiança passando de [0,31, 0,74] para ~[0,38, 0,66];
- **nenhuma tarefa é refeita**: verificado que a amostra de 270 contém as 100 já
  executadas, então apenas 170 são novas (~1.970 chamadas);
- a hipótese do overfit continua **exploratória** e será avaliada nas 170 novas
  isoladamente, com poder de apenas 36% — indicativo, não conclusivo.

Comando:

```bash
uv run arc-exp run --sample 270 --mode both --budget 7 --split evaluation \
  --run-id official
```

Resultados a preencher ao fim.

## Achados metodológicos das rodadas de calibração

As rodadas abaixo não entram na nota técnica como resultado, mas produziram restrições
que moldaram o desenho final. Os dados brutos foram descartados; o que ficou é o
aprendizado.

### A escolha do modelo decide o poder estatístico

O poder do teste pareado depende de haver tarefas que **uma** estratégia resolve e a
outra não. Modelos nos dois extremos destroem isso, de formas espelhadas:

| Modelo | Acurácia | Nenhuma resolve | Pares discordantes |
| --- | --- | --- | --- |
| `gemini-3.7-flash` (11 tarefas) | ~90% | ~0% | ~0 — resolve tudo na 1ª chamada |
| `gemini-3.5-flash-lite` (50 tarefas) | 26% / 28% | 66% | **7 (14%)** |
| `gemini-3.1-flash-lite` (37 tarefas) | 13,5% / 16,2% | 81% | 3 (8%) |

O modelo forte resolve na primeira geração — que é idêntica nas duas condições — e gera
só pares concordantes. O modelo fraco falha nas duas e gera pares concordantes também.
`gemini-3.5-flash-lite` é o ponto mais informativo entre os modelos alcançáveis, e é por
isso que a rodada oficial usa ele. **Não foi escolhido por conveniência de cota.**

### Modelos com raciocínio interno não controlável são inadequados

`gemma-4-26b-a4b-it` foi testado e abandonado. A partir da segunda iteração da condição
`critic`, passa a gastar **8.189 tokens pensando e 0 respondendo** — o pensamento
consome todo o `MAX_OUTPUT_TOKENS` antes de qualquer texto. Cinco chamadas consecutivas
produziram nada. A condição `sampling`, que sempre reenvia o prompt inicial, não sofre
disso: o gatilho é a **mensagem de revisão**, exatamente o que distingue a condição sob
teste.

Sem conserto: `thinking_config` responde `400 — Thinking budget is not supported for
this model`, e aumentar o teto de saída piora, porque o limite de 16.000 tokens/minuto
do Gemma já é menor que uma única chamada desta carga (~17.200 tokens). A latência
sozinha (174 s por chamada de revisão) já custaria 58 h na rodada.

**Erro de método que isso expôs:** o benchmark que aprovou o Gemma mediu 92,8 s e
`think=0` usando apenas o **prompt inicial**. O comportamento patológico só aparece nos
prompts de revisão. Avaliar um modelo para este experimento exige exercitar as duas
formas de prompt.

### O ganho do Crítico se dissolve ao descontar a primeira geração

Na rodada de 50 tarefas com `gemini-3.5-flash-lite`, o `critic` terminou +1 tarefa à
frente (14 contra 13, p = 1,0000 sobre 7 pares discordantes). Mas **5 das suas 14
vitórias vieram da primeira geração**, antes de qualquer crítica, contra 2 do
`sampling`. Essa chamada é idêntica nas duas condições em prompt e histórico; difere só
a temperatura. Descontadas, o placar atribuível ao ciclo de crítica fica **9 a 11,
favorecendo `sampling`**.

Isso não é ruído a ser eliminado: com temperaturas diferentes por definição, a primeira
amostra **faz parte** de cada estratégia. Mas a nota técnica precisa reportar o placar
com e sem esse desconto, porque a leitura muda de sinal.

### O Crítico custa o dobro em tokens pelo mesmo número de chamadas

2,56M tokens de entrada contra 1,33M do `sampling`, com 302 e 300 chamadas. O histórico
acumulado e o gabarito completo viajam a cada crítica. Por esse preço, produziu 3,52
programas por tarefa contra 6,00. **Se o orçamento fosse contado em tokens em vez de
chamadas, a comparação seria bem menos favorável ao Crítico** — ver a ameaça à validade
sobre a unidade do orçamento.

### A amostragem só converte orçamento em vantagem quando há sinal no treino

A diversidade é real: 7 de 7 programas distintos por tarefa a T=0,8. Mas em metade das
tarefas **todos** os candidatos empatam em zero pares de treino corretos — e com o
desempate pela primeira amostra, o best-of-N com orçamento 7 fica operacionalmente
idêntico a uma única tentativa. Nas tarefas difíceis do ARC o sinal de treino é fraco
demais para ranquear candidatos, que é justamente onde o Crítico tem informação que a
amostragem não tem.

### O overfit é o alvo certo e não foi convertido

Três tarefas reproduziram todos os pares de treino e erraram o teste. Nenhuma foi
resolvida pelo Crítico, apesar de serem exatamente os casos em que ver o gabarito
deveria ajudar.
