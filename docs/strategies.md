# As duas estratégias comparadas

O repositório responde a uma única pergunta: **dado um orçamento fixo de chamadas à
API por tarefa, é melhor diversificar ou iterar?**

Duas estratégias disputam exatamente o mesmo orçamento. Tudo o que não serve para
distinguir uma da outra foi removido do código.

## Definição

| | `sampling` — diversificar | `critic` — iterar |
| --- | --- | --- |
| Chamadas por tarefa | até N, todas do Gerador | até N, alternando Gerador e Crítico |
| Histórico entre chamadas | **nenhum** | completo no Gerador; Crítico sem memória |
| Prompt | `generator_initial`, idêntico a cada amostra | `generator_initial`, depois `generator_revision` |
| Temperatura | **0.8** (`SAMPLING_TEMPERATURE`) | **0.2** (`TEMPERATURE`) |
| Acesso ao gabarito do teste | nenhum agente | apenas o Crítico |
| Programas por orçamento de 7 | 7 | 4 |
| Critério de parada | reproduzir todos os pares de treino | idem |
| Seleção final | melhor no treino; empate → **primeira** amostra | melhor no treino; empate → **última** iteração |

Implementação: `runner.solve_task`. A condição está em `runner.Condition`; a
temperatura é escolhida por condição em `experiment.temperature_for`.

### `sampling` — best-of-N

Gasta o orçamento em largura. Cada chamada é uma conversa nova com o mesmo prompt
inicial: o modelo não sabe que já tentou antes, não vê o resultado da execução, não
recebe crítica. No fim, entre os candidatos gerados, vence o que reproduz mais pares
de treino.

É a estratégia que a literatura de síntese de programa chama de *amostragem com
verificador*, e é um baseline forte — não um espantalho. Se ela vencer, a conclusão é
que o orçamento rende mais em diversidade do que em correção guiada.

### `critic` — revisão guiada por oráculo

Gasta o orçamento em profundidade. O Gerador propõe uma regra e um programa; o
Crítico, que enxerga o gabarito do par de teste, aponta em que pontos a regra
enunciada contradiz a realidade — sem propor solução, sem escrever código, sem
reproduzir grades. O Gerador revisa com esse feedback e com o histórico completo da
conversa.

Cada ciclo completo custa duas chamadas, então com orçamento 7 saem 4 programas
contra os 7 da amostragem. A aposta é que a densidade informacional do feedback
compense a metade das tentativas.

## Decisões que precisam de justificativa

### Temperatura assimétrica

Com T=0.2, sete amostras do mesmo prompt tendem a ser quase idênticas: o best-of-N
degeneraria em uma única tentativa repetida sete vezes, e a comparação seria contra
um espantalho. Diversidade não é um detalhe de configuração da amostragem — é a
estratégia inteira.

O preço é que a temperatura vira mais um eixo de diferença entre as condições. Está
declarado em [experimental-decisions.md](experimental-decisions.md), seção 7.

### Desempate invertido

Em `critic`, iterações posteriores incorporam feedback, então é razoável que a última
vença empates. Em `sampling` não há progressão — a sétima amostra não é a priori
melhor que a primeira — então empates ficam com a primeira. Sem isso, amostrar mais
deslocaria a escolha por conta própria, o que daria à estratégia uma vantagem que não
vem da qualidade dos candidatos.

`runner._better` recebe `prefer_latest` para expressar exatamente essa diferença.

### Nenhuma estratégia usa o gabarito para escolher

O critério de parada e a seleção do candidato final olham **apenas** para os pares de
treino, nas duas condições. O par de teste é executado uma única vez, no fim, só para
medir. O Crítico influencia o raciocínio do Gerador, mas nunca escolhe por ele — é
essa restrição que impede a taxa de acerto da intervenção de virar um limite superior
de oráculo.

## O que este desenho não responde

`sampling` e `critic` diferem em quatro eixos ao mesmo tempo: existência de feedback,
acesso ao gabarito, orçamento gasto em paralelo ou em série, e temperatura. Um
resultado positivo sustenta a leitura pragmática — *gastar o orçamento deste jeito
rende mais acertos* — e **não** a leitura causal — *a assimetria de informação é o que
funciona*. Separar as causas exigiria condições adicionais, descritas em
[experimental-decisions.md](experimental-decisions.md), seção 9.
