
# Relatório Semanal - Semana 2

## 📌 Resumo
Nesta semana, as principais entregas envolveram a correção de um bug crítico no oráculo, a implementação de novos críticos e a execução de experimentos de calibração (30 tarefas) e avaliação (60 tarefas). Os resultados confirmaram que as variações de desempenho observadas até agora não são estatisticamente significativas, indicando ruído estatístico de amostra pequena.

## ✅ Atividades Concluídas

### Implementações e Correções
* O bug no `crítico-oráculo` foi corrigido, garantindo que a função `critic_request` agora receba o código candidato corretamente, não apenas a regra em linguagem natural.
* Foram implementados dois novos críticos de forma paralela (sem duplicar o loop de controle): `critic_no_oracle` (sem acesso ao gabarito) e `critic_cegis` (com acesso ao gabarito e respostas em vocabulário fechado com contraexemplo).
* Identificado e corrigido um bug de *encoding* que quebrava a leitura/escrita de arquivos no Windows; a correção foi aplicada em 6 arquivos e coberta com um teste de regressão.
* A CLI foi atualizada para suportar os novos parâmetros (`--mode critic-no-oracle`, `--mode critic-cegis`, `--mode all`).

### As quatro condições comparadas

Todas competem sob o **mesmo orçamento de chamadas de API por tarefa**.

| Condição | O que faz | Custo por ciclo |
| :--- | :--- | :--- |
| `sampling` | Gera N tentativas **independentes** (conversas novas, sem memória, temperatura alta pra diversificar). Fica com a que acerta mais pares de treino. | 1 chamada/tentativa |
| `critic` | Gerador propõe → Crítico vê o **gabarito do teste** e o **código candidato**, aponta contradições em prosa → Gerador revisa. Repete até acabar o orçamento. | 2 chamadas/ciclo |
| `critic_no_oracle` | Igual ao `critic`, mas o crítico **nunca vê o gabarito** — só código, regra e o resultado no treino. Verifica se código bate com o que a regra promete. | 2 chamadas/ciclo |
| `critic_cegis` | Igual ao `critic` (vê o gabarito), mas responde em formato fechado: um contraexemplo + um rótulo de correção (`WRONG_GEOMETRY`, `MISSING_CASE`, etc.) em vez de prosa livre. | 2 chamadas/ciclo |

Por isso `critic*` produz menos programas que `sampling` com o mesmo orçamento — cada rodada de crítica "come" uma chamada que `sampling` teria usado gerando mais uma tentativa.

## 📊 Experimentos e Resultados
Foram executadas duas rodadas experimentais: Calibração (30 tarefas, 4 condições) e Oficial (60 tarefas, 4 condições). Na rodada Oficial, a condição de `sampling` não precisou ser re-executada, pois foi reaproveitada das tarefas da rodada anterior.

### Resultado da calibração (30 tarefas — único conjunto completo)

| Condição           | Resolvidas | Acurácia | Consist. treino |
| :----------------- | :--------- | :------- | :-------------- |
| sampling           | 11/30      | 36,7%    | 40,0%           |
| critic (corrigido) | 7/30       | 23,3%    | 26,7%           |
| critic_no_oracle   | 8/30       | 26,7%    | 33,3%           |
| critic_cegis       | 6/30       | 20,0%    | 26,7%           |

Durante a execução de 60 tarefas, o progresso foi interrompido duas vezes por esgotamento de cota da API, e foi constatado que 3 das 9 chaves configuradas apresentavam erro 401 permanente. O problema foi contornado retomando o pipeline em múltiplas tentativas.

**Resultados da Rodada Oficial (60 tarefas):**

| Condição           | Acurácia | vs sampling (McNemar p) |
| :----------------- | :------- | :---------------------- |
| sampling           | 31,7%    | -                       |
| critic (corrigido) | 38,3%    | 0,2188                  |
| critic_no_oracle   | 28,3%    | 0,7539                  |
| critic_cegis       | 26,7%    | 0,4531                  |

*Análise Estatística:* Nenhuma das cinco comparações pré-registradas apresentou relevância estatística sob a correção de Bonferroni (α=0,01). A inversão dos resultados frente à rodada de calibração reforça que a diferença captada é ruído, consistente com o resultado nulo da rodada original de 270 tarefas.

## 🚧 Próximos Passos e Pendências
* Avaliar o tempo e o custo de estender o experimento para as 270 tarefas completas.


