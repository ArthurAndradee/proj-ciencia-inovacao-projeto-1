# Resultados — rodada oficial

**270 tarefas do ARC-AGI-1 · `gemini-3.5-flash-lite` · 21/08/2026 · commit `5fdda8d`**

> **A hipótese não se confirmou.** Sob orçamento fixo de chamadas, a revisão guiada por
> crítico-oráculo **não** superou a amostragem best-of-N: −0,7 pp, **p = 0,8877**
> (McNemar exato). O intervalo de confiança limita qualquer vantagem do Crítico a
> **+4,3 pp**.

Detalhes de desenho em [experimental-decisions.md](experimental-decisions.md) ·
execução passo a passo em [exemplo-execucao.md](exemplo-execucao.md) ·
rodadas de calibração em [calibracao.md](calibracao.md).

---

## 1. Hipótese

Sob um **orçamento fixo de chamadas à API**, é melhor gastar tudo em tentativas
independentes (*diversificar*) ou gastar parte do orçamento revisando a mesma tentativa
(*iterar*)?

| Condição | Estratégia | Temp. | Histórico |
| --- | --- | --- | --- |
| `sampling` | best-of-N: N tentativas independentes | 0,8 | nenhum |
| `critic` | gerar → criticar → revisar, em ciclo | 0,2 | acumulado |

O Crítico enxerga o gabarito do par de teste e devolve apenas contradições em linguagem
natural. **Esperava-se que a informação privilegiada compensasse as iterações a menos.**

## 2. Metodologia

**Desenho pareado:** as mesmas 270 tarefas rodam nas duas condições, com o mesmo
orçamento de 7 chamadas por tarefa. Amostra sorteada de `evaluation` com seed 20260814,
**declarada antes da execução**.

**Acurácia.** O candidato final é o programa com mais pares de treino corretos; ele roda
no par de teste e o acerto exige a grade inteira idêntica. O gabarito do teste **nunca**
participa da seleção — se participasse, a métrica viraria um limite superior de oráculo.

**McNemar exato.** Teste para desenhos pareados: descarta as tarefas em que as duas
condições concordam e pergunta se as discordâncias se dividem por acaso.

```
p = 2 · P(X ≤ min(a,b)),  X ~ Binomial(a+b, ½)
a = 24 (só o Crítico) · b = 26 (só a amostragem) · p = 0,8877
```

Versão exata em vez da aproximação qui-quadrado, pouco confiável com poucas discordâncias.

**Intervalo de confiança (Wilson)**, sobre a proporção de discordâncias a favor do
Crítico. Escolhido em vez do Wald, que subestima o erro e pode produzir limites fora de
[0, 1]:

```
       p̂ + z²/(2n) ± z·√( p̂(1−p̂)/n + z²/(4n²) )
IC₉₅ = ────────────────────────────────────────────       p̂ = 24/50 · n = 50 · z = 1,96
                     1 + z²/n

IC₉₅ = 0,35 a 0,61   →   em acurácia: −5,6 pp a +4,3 pp,  via d·(2π−1)/n
```

**Fisher exato** nas comparações não pareadas (overfit entre condições).

## 3. Resultados

| Condição | Resolvidas | Acurácia | Consist. treino | Programas/tarefa | Tokens |
| --- | --- | --- | --- | --- | --- |
| `sampling` | 88/270 | **32,6%** | 35,6% | 5,43 | 7,6 M |
| `critic` | 86/270 | **31,9%** | 35,6% | 3,30 | 12,6 M |

**Comparação pareada** — as células em destaque são as discordâncias, as únicas que
informam qual estratégia é melhor:

| | `critic` resolveu | `critic` falhou |
| --- | --- | --- |
| **`sampling` resolveu** | 62 | **26** |
| **`sampling` falhou** | **24** | 158 |

| | |
| --- | --- |
| Discordantes | 50 (18,5%), divididos 24 · 26 |
| Ganho líquido | −2 tarefas (−0,7 pp) |
| **McNemar exato** | **p = 0,8877** |
| **IC 95% da diferença** | **−5,6 pp a +4,3 pp** |

## 4. Interpretação

**O resultado é nulo, e bem medido.** As duas condições resolvem quase o mesmo conjunto:
62 tarefas em comum, 158 em que ambas falham. As 50 discordâncias se dividem ao meio. A
diferença chegou a inverter de sinal entre a análise interina de 100 tarefas (+1 para o
Crítico) e o conjunto de 270 (−2) — comportamento de ruído, não de efeito.

O valor do IC é dizer **quanto** o efeito não pode ser: qualquer vantagem do Crítico está
limitada a 4,3 pp. É a diferença entre *não encontramos efeito* e *não conseguimos medir*.

**Metade das vitórias não pertence a nenhuma estratégia.** A primeira geração é idêntica
nas duas condições — mesmo prompt, histórico vazio, só a temperatura difere:

| | vitórias | na 1ª geração | atribuíveis ao ciclo |
| --- | --- | --- | --- |
| `sampling` | 88 | 44 | **44** |
| `critic` | 86 | 42 | **44** |

Descontada, o placar é **44 a 44**; nas 206 tarefas que ela não resolveu, 18 a 15 para o
Crítico (p = 0,7283). **O experimento só discrimina de fato em 206 das 270 tarefas** — o
achado mais relevante sobre o próprio desenho.

**O Crítico faz o que promete, mas não converte.** Produz programas com a mesma
consistência de treino usando **quase metade** dos programas (3,30 contra 5,43 por
tarefa), o que confirma que a revisão dirigida funciona como mecanismo. Só que isso não
vira acurácia no teste.

A explicação candidata — que o Crítico causaria mais *overfit* — foi registrada como
exploratória e testada nas 170 tarefas novas isoladamente: **não se replicou** (23,3%
na interina, 15,2% na réplica, p = 0,6173). Era ruído.

**Limitações.**

1. Metade do resultado vem de uma chamada comum às duas condições.
2. O orçamento é medido em chamadas, não em tokens — e o Crítico consome **66% mais
   tokens** (146k contra 86k por tarefa resolvida). Sob orçamento em tokens, perderia.
3. Execução única por tarefa: parte da variação é ruído do modelo, mitigado pelo
   pareamento, não eliminado.
4. O oráculo não é autônomo — mede o valor da validação por oposição, não um sistema
   utilizável em produção.

---

<sub>270 tarefas × 2 condições em 20 min · 1.812 chamadas · 7 chaves de API em paralelo
(258–259 chamadas cada) · 2 chaves rejeitadas e descartadas automaticamente do pool ·
nenhuma cota esgotada.</sub>

```bash
uv run arc-exp run --sample 270 --mode both --budget 7 --split evaluation --run-id official
```
