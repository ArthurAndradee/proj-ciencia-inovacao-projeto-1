# Piloto de injeção — o gabarito no prompt do gerador

**50 tarefas do ARC-AGI-1 · `gemini-3.5-flash-lite` · 21/08/2026 · orçamento 7 chamadas**

> Entregar a resposta do teste ao gerador, 105 vezes, leva a acurácia de 30% para 50% —
> **e 25 das 42 tarefas que receberam o gabarito continuaram erradas.** O gargalo do Crítico
> não é a informação que ele não pode transmitir.

Subconjunto das 270 tarefas da [rodada oficial](results.md) (os 50 primeiros ids do
`manifest.json`), mesmo orçamento e mesmo modelo, para parear com `sampling` e `critic` já
executados.

## 1. Os braços

| Braço | O que o gerador recebe na revisão |
| --- | --- |
| `sampling` | nada — N tentativas independentes |
| `critic` | prosa do Crítico, com grades e código redigidos por `guards.sanitize` |
| `counterexample` | idem + **as grades-alvo dos pares de treino que o programa errou** |
| `oracle` | idem + **a grade-alvo do par de teste** |

As grades são renderizadas pelo runner a partir do gabarito, não pedidas ao modelo
(`prompts.counterexample_block`). O que vaza é exatamente o que foi escolhido, idêntico em
toda chamada, e `guards.sanitize` continua significando "prosa que o Crítico não deveria ter
escrito" — a divulgação deliberada é contabilizada à parte, em `injected_train` e
`injected_test`.

`oracle` **não é uma estratégia e sua acurácia não é comparável**: com o alvo no prompt o
gerador pode gravá-lo no código. É um teto, e vale pelo que o teto revela.

## 2. Resultados

| Braço | Resolvidas | Acurácia | Consist. treino | McNemar vs. `sampling` | Tokens/resolvida |
| --- | --- | --- | --- | --- | --- |
| `sampling` | 17/50 | **34,0%** | 38,0% | — | 76k |
| `critic` | 15/50 | **30,0%** | 40,0% | −2 · p = 0,6875 | 148k |
| `counterexample` | 15/50 | **30,0%** | 38,0% | −2 · p = 0,6875 | 155k |
| `oracle` | 25/50 | **50,0%** | 44,0% | +8 · p = 0,0963 | 103k |
| `oracle` sem transcrições | 22/50 | **44,0%** | — | +5 · p = 0,3018 | — |

**Transcrição direta é rara.** Varrendo os literais de lista de cada programa final por AST,
**3 dos 50** embutem a grade-alvo inteira (`136b0064`, `20818e16`, `2037f2c7`) — as três
resolvidas. Descontadas, `oracle` fica em 44%, exatamente sua consistência de treino. O modelo
recebeu a resposta 105 vezes e copiou-a 3.

## 3. O que o piloto mostra

**1. Explicitar o treino não faz nada.** `counterexample` empata com `critic` em acurácia
(30% contra 30%) e em iterações (3,12 contra 3,12), com discordância de 3 a 3 — troca de
tarefas, não ganho. Era o resultado previsto: o gerador **já** tem todos os pares de treino no
histórico acumulado, então o braço testava saliência, não informação. Saliência não é o
gargalo.

**2. Nem o gabarito do teste resolve metade dos casos.** 42 tarefas chegaram a uma rodada de
revisão e receberam o alvo. **25 delas terminaram erradas.** O gerador tinha a resposta na
janela de contexto e não conseguiu escrever um programa que a produzisse.

**3. Isso realoca a explicação do resultado nulo.** A hipótese de que o Crítico falhou por
ter um canal estreito demais não se sustenta: alargado até o limite — sem guard, sem prosa,
a grade literal — o ganho sobre `sampling` é +8 tarefas com p = 0,0963, e cai para +5 com
p = 0,3018 quando as transcrições saem. O limite não está em *quanta informação chega ao
gerador*, e sim em *quanto dele consegue virar programa*. Um crítico melhor não move isso.

**4. O teto do desenho inteiro é baixo.** Se com o gabarito na mão o sistema chega a 44–50%,
nenhum arranjo de gerador e crítico dentro deste desenho passa muito disso. A distância entre
34% (`sampling`) e ~50% (oráculo) é todo o espaço que qualquer estratégia de feedback poderia
disputar — e a rodada oficial mostrou que o Crítico não ocupa nada dele.

**Limitações.** 50 tarefas: nenhuma das comparações atinge significância, e o intervalo em
torno de 50% é largo. O piloto responde "o mecanismo funciona e o teto é baixo", não "o
ganho do oráculo é X". Execução única por tarefa. A detecção de transcrição por AST pega
literais explícitos, não uma grade reconstruída por aritmética.

## 4. Achado colateral no guard

`guards._GRID_ROW` exige **três ou mais** inteiros na linha, então uma grade de largura ≤ 2
passa intacta. No split `evaluation` são 9 tarefas em 400 com alvo de teste assim, **6 delas
entre as 270 da rodada oficial** — nessas, a prosa do Crítico nunca foi de fato filtrada.
Alargar o padrão redigiria frases legítimas como "examples 2 3", então o comportamento fica
como está, agora fixado por teste em `tests/test_guards.py`.

---

```bash
uv run arc-exp run --tasks-file results/pilot50.txt --mode counterexample --budget 7 --run-id oracle-pilot50
uv run arc-exp run --tasks-file results/pilot50.txt --mode oracle         --budget 7 --run-id oracle-pilot50
uv run arc-exp report --run-dir results/runs/oracle-pilot50
```
