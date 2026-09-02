# Exemplos de acerto e falha — críticos novos

> Casos reais extraídos de `results/runs/critic-official/` (rodada de 60 tarefas,
> `docs/results.md` Parte A). Nenhum texto foi editado — regras, críticas e classes de
> correção são exatamente o que o modelo produziu. Escolhidos por serem didaticamente
> claros, não por serem os mais favoráveis a nenhuma condição.

## Caso 1 — tarefa `070dd51e`: o mecanismo funcionando (e uma limitação do CEGIS)

**O que a tarefa pede**: para cada par de pixels da mesma cor que compartilham linha ou
coluna, desenhar uma linha conectando-os. O detalhe que quebra soluções ingênuas: quando
linhas de cores diferentes se cruzam, a linha **vertical** tem prioridade sobre a
horizontal no ponto de interseção — um detalhe que não é óbvio a partir só dos exemplos.

| Condição | Resultado | Chamadas | Iterações |
| --- | --- | --- | --- |
| `sampling` | ✗ não resolveu | 7 | 7 (todas as tentativas erram do mesmo jeito) |
| `critic` (oráculo, corrigido) | ✓ resolveu | 3 | 2 |
| `critic_no_oracle` (sem oráculo) | ✓ resolveu | 3 | 2 |
| `critic_cegis` (oráculo, formato fechado) | ✗ não resolveu | 7 | 4 |

**`sampling` fica preso no mesmo bug nas 7 tentativas independentes** — sem nunca saber
que errou, cada tentativa reinventa uma variação da mesma regra incompleta (nenhuma
menciona o que fazer nos cruzamentos).

**`critic_no_oracle` resolve em 2 rodadas — sem nunca ver o gabarito**. A crítica, na
íntegra:

> *"The code faithfully implements the stated rule by independently drawing horizontal
> and vertical line segments for all matching non-zero colors, overwriting grid cells
> where different colors intersect without any prioritization."*

Isso é comparação de **código com código** (a implementação bate com a regra), não
comparação com o gabarito — e já é suficiente pra apontar exatamente o problema. O
Gerador corrige na rodada seguinte ("vertical lines have priority over horizontal") e
acerta o treino inteiro.

**`critic` (oráculo, corrigido) chega à mesma correção**, também em 2 rodadas, com uma
crítica de teor equivalente. Ou seja: nesta tarefa, ter acesso ao gabarito não trouxe
vantagem sobre não ter — o problema era detectável só pela consistência interna do
código.

**`critic_cegis` falha, apesar de ter acesso ao gabarito.** Suas quatro críticas,
resumidas ao rótulo fechado:

> Rodada 1: `WRONG_TRANSFORM` · Rodada 2: *"overlapping lines from different colors
> overwrite each other incorrectly instead of preserving the proper color precedence"*
> + `WRONG_TRANSFORM` · Rodada 3: `WRONG_TRANSFORM` (uma frase só) · Rodada 4: (orçamento
> acaba antes de nova crítica)

A rodada 2 chega perto de dizer a coisa certa ("preserving proper color precedence"),
mas nunca nomeia **qual** cor tem precedência sobre qual — a informação que fez a
diferença nos outros dois críticos ("vertical sobre horizontal") nunca aparece de forma
utilizável. O Gerador troca de hipótese a cada rodada sem convergir.

**Leitura**: um caso onde a *forma* do feedback importa mais que o *acesso* à
informação — indício qualitativo alinhado ao resultado quantitativo da Parte A
(`critic` vs `critic_cegis`, a comparação mais próxima de significância entre as 5).

## Caso 2 — tarefa `281123b4`: uma vitória que não prova nada sobre o mecanismo

| Condição | Resultado | Chamadas | Iterações |
| --- | --- | --- | --- |
| `sampling` | ✗ não resolveu | 7 | 7 |
| `critic` (corrigido) | ✓ resolveu | **1** | **1** |
| `critic_no_oracle` | ✓ resolveu | **1** | **1** |
| `critic_cegis` | ✗ não resolveu | 7 | 4 |

À primeira vista parece outra vitória dos críticos novos. Mas `critic` e
`critic_no_oracle` resolveram **na primeira geração** — nenhuma crítica foi sequer
chamada (`iters=1`). A primeira geração usa exatamente o mesmo prompt em todas as
condições; a única diferença é a temperatura (`critic*` roda a 0,2, `sampling` a 0,8).
Aqui, a temperatura baixa acertou de primeira; a alta, mais exploratória, errou sete
vezes seguidas na mesma tarefa.

**Isso não é evidência de que os críticos "funcionaram"** — é exatamente o "desconto da
primeira geração" que a Parte B já documentava para o crítico original ("metade das
vitórias não pertence a nenhuma estratégia", `docs/results.md` B.4). Incluído aqui de
propósito, como lembrete de que nem toda vitória isolada é sinal do mecanismo em ação —
é por isso que a conclusão do projeto se apoia no teste pareado sobre a amostra inteira,
não em casos individuais.

## O que esses dois casos, juntos, ensinam

1. O bug do oráculo (Caso 1) tinha efeito real: sem o código, nenhum dos dois críticos
   antigos conseguiria citar "the code implements..." — a crítica ficaria restrita à
   regra em prosa, como na rodada oficial original.
2. Acesso ao gabarito **não é** o fator decisivo em todo caso — `critic_no_oracle`
   resolveu o Caso 1 tão bem quanto `critic`.
3. A forma do feedback importa: o mesmo acesso à informação (`critic` vs `critic_cegis`)
   produziu resultados opostos no Caso 1, porque o vocabulário fechado não tem como
   expressar "vertical tem prioridade sobre horizontal".
4. Nem toda vitória é sinal — o Caso 2 é ruído de temperatura, não mérito do crítico.
   Distinguir os dois é o motivo de todo o aparato estatístico da Parte A.
