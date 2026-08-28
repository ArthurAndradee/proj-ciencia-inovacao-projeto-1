# Resultados

Detalhes de desenho em [experimental-decisions.md](experimental-decisions.md) ·
execução passo a passo em [exemplo-execucao.md](exemplo-execucao.md) ·
rodadas de calibração em [calibracao.md](calibracao.md).

---

# Parte A — Crítico corrigido + dois críticos novos

**58 de 60 tarefas-alvo do ARC-AGI-1 · `gemini-3.5-flash-lite` · 28/08/2026 · commit
`c7f12b4`**

> **Nenhuma das 5 comparações pré-registradas é significativa sob a correção de
> Bonferroni (α = 0,05/5 = 0,01).** A mais próxima — `critic` vs `critic_cegis` —
> chega a p = 0,0391 sem correção, o que pareceria significativo a α = 0,05 isolado,
> mas **não** sobrevive à correção para as 5 comparações simultâneas pré-registradas em
> `experimental-decisions.md` §14. Com o crítico corrigido (agora vendo o código, não só
> a regra), a direção observada nesta amostra favorece `critic` sobre `sampling`
> (+6,9 pp), o oposto do sinal visto na calibração de 30 tarefas — instabilidade
> consistente com o tamanho de amostra ainda pequeno frente às 270 tarefas da Parte B.

## A.1 O que mudou frente à Parte B (abaixo)

Esta rodada usa o crítico **corrigido** (`prompts.critic_request` agora inclui o código
candidato, não só a regra — `experimental-decisions.md` §13) e adiciona duas condições:
`critic_no_oracle` (nunca vê o gabarito do teste) e `critic_cegis` (vê o gabarito, mas
responde em vocabulário fechado — um contraexemplo + uma classe de correção, no espírito
de CEGIS). Desenho completo em `experimental-decisions.md` §14.

`sampling` é reaproveitado da rodada da Parte B (mesma seed, mesmo split, mesmas 270
tarefas já incluem as 58 usadas aqui) — não foi re-executado.

## A.2 Metodologia

Mesmo desenho pareado da Parte B (McNemar exato, IC de Wilson), estendido para uma
**família de 5 comparações pré-registradas** em vez de uma só:

| # | Par | Isola |
| --- | --- | --- |
| 1 | `sampling` vs `critic` | hipótese original, com o bug corrigido |
| 2 | `sampling` vs `critic_no_oracle` | valor da crítica estruturada sem oráculo |
| 3 | `sampling` vs `critic_cegis` | valor do oráculo em forma de contraexemplo único |
| 4 | `critic` vs `critic_no_oracle` | valor do acesso ao gabarito, mantendo a forma prosa |
| 5 | `critic` vs `critic_cegis` | valor da forma estruturada, mantendo o acesso ao gabarito |

Com 5 testes simultâneos sobre os mesmos dados, a correção de **Bonferroni** (α =
0,05/5 = 0,01) evita inflar o erro tipo I — distinta da correção de Pocock usada na
Parte B (aquela é para múltiplas *olhadas no tempo*, esta é para múltiplas comparações
*simultâneas*). `critic_no_oracle` vs `critic_cegis` fica fora da família pré-registrada
(varia duas dimensões ao mesmo tempo) e não é testada.

**Escala menor que a Parte B, declarada como limitação, não escondida.** A amostra-alvo
era 60 tarefas (não 270) — uma escolha deliberada de calibração/tempo diante de cota de
API limitada (ver §A.4) — e a rodada parou em **58/60**: a cota diária se esgotou
faltando 2 tarefas (`31adaf00`, `3490cc26`), que não têm registro nas três condições
novas. Os dados abaixo cobrem as 58 completas.

## A.3 Resultados

| Condição | Resolvidas (de 58) | Acurácia | Consist. treino | Programas/tarefa | Tokens/tarefa |
| --- | --- | --- | --- | --- | --- |
| `sampling` | 19/58 | 32,8% | 37,9% | 5,28 | ~25,0 k |
| `critic` (corrigido) | 23/58 | **39,7%** | 43,1% | 3,09 | ~43,0 k |
| `critic_no_oracle` | 17/58 | 29,3% | 34,5% | 3,28 | ~40,1 k |
| `critic_cegis` | 16/58 | 27,6% | 31,0% | 3,29 | ~45,1 k |

**As 5 comparações pareadas:**

| Par | Discordantes | McNemar exato (p) | IC 95% da diferença | Significativo (α=0,01)? |
| --- | --- | --- | --- | --- |
| `sampling` vs `critic` | 6 (1×5) | 0,2188 | −1,3 pp a +9,7 pp | não |
| `sampling` vs `critic_no_oracle` | 10 (6×4) | 0,7539 | −11,4 pp a +6,5 pp | não |
| `sampling` vs `critic_cegis` | 7 (5×2) | 0,4531 | −10,1 pp a +3,4 pp | não |
| `critic` vs `critic_no_oracle` | 10 (8×2) | 0,1094 | −15,3 pp a +0,3 pp | não |
| `critic` vs `critic_cegis` | 9 (8×1) | **0,0391** | −14,9 pp a −2,0 pp | **não** (não sobrevive a α=0,01) |

## A.4 Interpretação

**A direção inverteu frente à calibração de 30 tarefas — e isso é o próprio ponto.** Na
calibração, `critic` corrigido tinha acurácia *abaixo* de `sampling` (23,3% contra
36,7%); aqui, com quase o dobro de tarefas, está *acima* (39,7% contra 32,8%), e ainda
assim sem significância em nenhum dos dois tamanhos de amostra. As duas leituras não são
contraditórias — são o mesmo sintoma: com n=30 ou n=58, a estimativa de acurácia tem
variância grande demais para revelar direção de forma confiável. É por isso que a Parte B
precisou de 270 tarefas para ter poder estatístico, e por isso esta rodada não pretende
substituir aquela conclusão — só testar se o crítico corrigido e os críticos novos
merecem ser levados à mesma escala.

**`critic_cegis` teve o pior desempenho entre os quatro**, e a única comparação que
chega perto de significância isolada (`critic` vs `critic_cegis`, p=0,0391) vai contra
ele — mas não sobrevive à correção pré-registrada para 5 comparações simultâneas.
Reportado como um sinal a acompanhar numa amostra maior, não como conclusão.

**Vocabulário fechado do CEGIS se manteve estável**: nas 58 tarefas, todas as críticas
de `critic_cegis` respeitaram o rótulo fechado de `CORRECTION CLASS` (mesmo padrão de
72/72 observado na calibração) — o formato estruturado funciona mecanicamente, o que
não se traduziu em vantagem de acurácia nesta amostra.

**Limitações desta parte.**

1. **Escala menor que a Parte B** (58-60 tarefas contra 270) — poder estatístico baixo
   por desenho; nenhuma das 5 comparações deveria ser lida como conclusiva.
2. **2 tarefas pendentes** (`31adaf00`, `3490cc26`) por esgotamento de cota diária —
   podem ser adicionadas depois com `arc-exp run --tasks-file
   results/runs/critic-official/task-list-60.txt --mode all --budget 7 --run-id
   critic-official`.
3. **3 das 9 chaves de API usadas nesta rodada retornam 401** ("bound service account
   deleted or disabled" / credenciais inválidas) — reduz a capacidade disponível para
   qualquer extensão futura; não afeta a corretude dos dados coletados.
4. **`critic` consome ~72% mais tokens por tarefa que `sampling`** (~43,0k contra
   ~25,0k) nesta amostra — mesma ameaça à validade já registrada na Parte B sobre a
   unidade do orçamento.
5. Mesmas limitações estruturais da Parte B (execução única por tarefa, oráculo não
   autônomo) se aplicam aqui.

```bash
uv run arc-exp run --tasks-file results/runs/critic-official/task-list-60.txt \
  --mode all --budget 7 --run-id critic-official
```

---

# Parte B — rodada oficial original (crítico pré-correção)

**270 tarefas do ARC-AGI-1 · `gemini-3.5-flash-lite` · 21/08/2026 · commit `5fdda8d`**

> **A hipótese não se confirmou.** Sob orçamento fixo de chamadas, a revisão guiada por
> crítico-oráculo **não** superou a amostragem best-of-N: −0,7 pp, **p = 0,8877**
> (McNemar exato). O intervalo de confiança limita qualquer vantagem do Crítico a
> **+4,3 pp**.

> **Nota.** Esta parte descreve a rodada com o Crítico **antes** da correção do bug de
> acesso ao código (`experimental-decisions.md` §13) — o Crítico via só a regra em
> linguagem natural, nunca o código candidato. Mantida aqui como o resultado em escala
> completa (270 tarefas) e como baseline metodológico; a Parte A acima é o que muda com
> a correção e os críticos novos, ainda em escala reduzida.

## B.1 Hipótese

Sob um **orçamento fixo de chamadas à API**, é melhor gastar tudo em tentativas
independentes (*diversificar*) ou gastar parte do orçamento revisando a mesma tentativa
(*iterar*)?

| Condição | Estratégia | Temp. | Histórico |
| --- | --- | --- | --- |
| `sampling` | best-of-N: N tentativas independentes | 0,8 | nenhum |
| `critic` | gerar → criticar → revisar, em ciclo | 0,2 | acumulado |

O Crítico enxerga o gabarito do par de teste e devolve apenas contradições em linguagem
natural. **Esperava-se que a informação privilegiada compensasse as iterações a menos.**

## B.2 Metodologia

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

## B.3 Resultados

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

## B.4 Interpretação

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
