# Achados das rodadas de calibração

Rodadas anteriores à oficial. Não entram na nota técnica como resultado, mas produziram
as restrições que moldaram o desenho final. Os dados brutos foram descartados; o que
ficou é o aprendizado. O resultado do experimento está em [results.md](results.md).

## A escolha do modelo decide o poder estatístico

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

## Modelos com raciocínio interno não controlável são inadequados

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

## O ganho do Crítico se dissolve ao descontar a primeira geração

Na rodada de 50 tarefas com `gemini-3.5-flash-lite`, o `critic` terminou +1 tarefa à
frente (14 contra 13, p = 1,0000 sobre 7 pares discordantes). Mas **5 das suas 14
vitórias vieram da primeira geração**, antes de qualquer crítica, contra 2 do
`sampling`. Essa chamada é idêntica nas duas condições em prompt e histórico; difere só
a temperatura. Descontadas, o placar atribuível ao ciclo de crítica fica **9 a 11,
favorecendo `sampling`**.

Isso não é ruído a ser eliminado: com temperaturas diferentes por definição, a primeira
amostra **faz parte** de cada estratégia. Mas a nota técnica precisa reportar o placar
com e sem esse desconto, porque a leitura muda de sinal.

## O Crítico custa o dobro em tokens pelo mesmo número de chamadas

2,56M tokens de entrada contra 1,33M do `sampling`, com 302 e 300 chamadas. O histórico
acumulado e o gabarito completo viajam a cada crítica. Por esse preço, produziu 3,52
programas por tarefa contra 6,00. **Se o orçamento fosse contado em tokens em vez de
chamadas, a comparação seria bem menos favorável ao Crítico** — ver a ameaça à validade
sobre a unidade do orçamento.

## A amostragem só converte orçamento em vantagem quando há sinal no treino

A diversidade é real: 7 de 7 programas distintos por tarefa a T=0,8. Mas em metade das
tarefas **todos** os candidatos empatam em zero pares de treino corretos — e com o
desempate pela primeira amostra, o best-of-N com orçamento 7 fica operacionalmente
idêntico a uma única tentativa. Nas tarefas difíceis do ARC o sinal de treino é fraco
demais para ranquear candidatos, que é justamente onde o Crítico tem informação que a
amostragem não tem.

## O overfit é o alvo certo e não foi convertido

Três tarefas reproduziram todos os pares de treino e erraram o teste. Nenhuma foi
resolvida pelo Crítico, apesar de serem exatamente os casos em que ver o gabarito
deveria ajudar.

## Calibração dos críticos novos e do bug corrigido (28/08/2026)

30 tarefas de `evaluation`, seed 20260814, `BUDGET_CALLS=7`, `gemini-3.5-flash-lite` nos
dois papéis, `--mode all` (as quatro condições). Commit `45a4f8e` + as mudanças de
`critic_request`/`CriticSpec`/prompts ainda não commitadas no momento da rodada — dados
de calibração, não a rodada oficial. Manifesto e JSONL em
`results/runs/critic-calibration/` (não versionado, como as demais rodadas fora de
`official/`).

**O bug estava mesmo lá, e a correção funciona.** Inspecionando `critic_raw` das
críticas: *"The stated rule and code incorrectly assume an intersection-based logical
operation... the code implements a simpler neighborhood check for any cell adjacent to
both a 4 and a 5, converting many incorrect cells..."* — o Crítico agora fala do que **o
código faz**, não só da regra enunciada. Antes da correção isso era estruturalmente
impossível, porque o código nunca chegava ao prompt.

**O vocabulário fechado do CEGIS se sustentou.** Das 72 críticas emitidas por
`critic_cegis` na rodada, **72/72** trouxeram um rótulo válido de `CORRECTION CLASS`
(`MISSING_CASE | WRONG_TRANSFORM | WRONG_GEOMETRY | WRONG_COLOR_MAP | WRONG_SCOPE |
OTHER`). O risco levantado no plano — o modelo fugir do vocabulário — não se
confirmou nesta amostra.

**Nenhum erro de execução, nenhum vazamento.** `Errors=0` e `Leaks=0` nas quatro
condições (só 1 truncamento em `critic_cegis`, sem impacto). O orçamento ímpar de 7 se
comportou como esperado nas três condições de crítico (`cri=3 gen=4` ou `cri=2 gen=4`
nos casos que não pararam cedo).

**Resultado agregado — nenhuma condição bateu `sampling`, e nenhuma diferença é
significativa nesta escala (n=30):**

| Condição | Resolvidas | Acurácia | Consist. treino |
| --- | --- | --- | --- |
| `sampling` | 11/30 | 36,7% | 40,0% |
| `critic` (corrigido) | 7/30 | 23,3% | 26,7% |
| `critic_no_oracle` | 8/30 | 26,7% | 33,3% |
| `critic_cegis` | 6/30 | 20,0% | 26,7% |

| Par | Discordantes | McNemar exato |
| --- | --- | --- |
| `sampling` vs `critic` | 6 (5×1) | p = 0,2188 |
| `sampling` vs `critic_no_oracle` | 5 (4×1) | p = 0,3750 |
| `sampling` vs `critic_cegis` | 7 (6×1) | p = 0,1250 |
| `critic` vs `critic_no_oracle` | 9 (4×5) | p = 1,0000 |
| `critic` vs `critic_cegis` | 7 (4×3) | p = 1,0000 |

Nenhum p cruza nem o α = 0,05 nominal, muito menos o α = 0,01 de Bonferroni da família
pré-registrada — **como esperado numa calibração de 30 tarefas**, que não tem poder para
detectar o que a rodada oficial de 270 já mostrou ser um efeito pequeno (McNemar 100→270
em `experimental-decisions.md` §12). O sinal direcional (as três condições de crítico
abaixo de `sampling`) é consistente com o resultado nulo/levemente negativo da rodada
oficial — não há indício de que o bug corrigido, o crítico sem oráculo ou o CEGIS
mudem o quadro qualitativo.

**Problema operacional: 3 das 9 chaves foram rejeitadas pela API** (`key4`, `key7`,
`key8` — `REJECTED by the API`, 0 chamadas cada) e uma quarta (`key5`) esgotou a cota do
modelo após só 8 chamadas. Das 9, apenas 5 contribuíram de fato (`key1`, `key2`,
`key3`, `key6`, `key9`, 133 chamadas cada). Isso não afetou a corretude da rodada — o
pool falha para a próxima chave automaticamente — mas reduz a capacidade real para
~5/9 do nominal. Antes de uma rodada em escala 270 (que custaria até ~7.560 requisições
em `--mode all`, contra 1.400 da rodada oficial de 2 condições), vale conferir se as
chaves rejeitadas pertencem a um projeto sem free tier ou têm algum problema de
cadastro — ver `docs/usage.md` §5.

**Decisão pendente.** Os dados de calibração não mostram nenhum sinal (nem positivo nem
claramente negativo) forte o bastante para decidir sozinho se vale estender para 270
tarefas — essa é uma escolha de custo/tempo do projeto, não uma conclusão que os dados
imponham. Ver a pergunta feita ao usuário no acompanhamento desta sessão.
