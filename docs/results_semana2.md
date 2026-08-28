
# Relatório Semanal - Semana 2

## Recapitulação
> Dado um **orçamento fixo de chamadas a um LLM**, é melhor gastar esse orçamento **diversificando** (várias tentativas independentes) ou **iterando** (uma tentativa revisada por um Agente Crítico)?

### O ciclo de uma tarefa

```
Gerador propõe regra + código
        │
        ▼
Executor roda o código nos pares de treino (sandbox isolado)
        │
        ├── acertou tudo? ──────────────────────────► para (train_consistent)
        ├── orçamento esgotado? ────────────────────► para (budget_exhausted)
        │
        ▼
Crítico avalia (uma das 3 variantes) ──► filtro anti-vazamento ──► volta pro Gerador
```

## 📌 Resumo
Nesta semana, as principais entregas envolveram a correção de um bug crítico no oráculo, a implementação de novos críticos e a execução de experimentos de calibração (30 tarefas) e avaliação (60 tarefas). Os resultados confirmaram que as variações de desempenho observadas até agora não são estatisticamente significativas, indicando ruído estatístico de amostra pequena.

## ✅ Atividades Concluídas

### Implementações e Correções
* O bug no `crítico-oráculo` foi corrigido, garantindo que a função `critic_request` agora receba o código candidato corretamente, não apenas a regra em linguagem natural.
* Foram implementados dois novos críticos de forma paralela (sem duplicar o loop de controle): `critic_no_oracle` (sem acesso ao gabarito) e `critic_cegis` (com acesso ao gabarito e respostas em vocabulário fechado com contraexemplo).

<table>
<tr><th>Antes</th><th>Depois</th></tr>
<tr>
<td>

```python
def critic_request(
    task, rule, result
):
    return (
        f"...\n"
        f"RULE: {rule}\n"
        f"...\n"
    )
```

</td>
<td>

```python
def critic_request(
    task, rule, code, result
):
    return (
        f"...\n"
        f"RULE: {rule}\n"
        f"CODE:\n```python\n{code}\n```\n"
        f"...\n"
    )
```

</td>
</tr>
</table>

O Crítico nunca recebia `proposal.code` — só a regra em prosa e o placar de acerto no
treino. Ele julgava uma **descrição** do algoritmo, nunca o algoritmo em si. A rodada
oficial de 270 tarefas rodou inteira sob esse bug.
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

### Resultado consolidado (60/60 tarefas, rodada fechada)

| Condição | Resolvidas | Acurácia | Consist. treino | Tokens/tarefa |
|---|---|---|---|---|
| `sampling` | 19/60 | 31,7% | 36,7% | ~25,8 k |
| `critic` (corrigido) | 23/60 | **38,3%** | 41,7% | ~44,3 k |
| `critic_no_oracle` | 17/60 | 28,3% | 33,3% | ~41,6 k |
| `critic_cegis` | 16/60 | 26,7% | 30,0% | ~46,3 k |


*Análise Estatística:* Nenhuma das cinco comparações pré-registradas apresentou relevância estatística sob a correção de Bonferroni (α=0,01). A inversão dos resultados frente à rodada de calibração reforça que a diferença captada é ruído, consistente com o resultado nulo da rodada original de 270 tarefas.

### Atualização em andamento — extensão para 270 tarefas

Depois de fechar as 60 tarefas, iniciamos uma extensão para a mesma escala da rodada
original (270 tarefas), reaproveitando o `sampling` já existente. **Ainda em
andamento** no momento da escrita — travado por cota diária de API, retomado a cada
folga disponível. Leitura **interina**, não final:

| Condição | Acurácia (n=110, parcial) | vs `sampling` |
|---|---|---|
| `critic` | ~37,5% | +6,7 pp, p=0,1185 |
| `critic_no_oracle` | ~31,7% | +1,0 pp, p=1,0000 |
| `critic_cegis` | ~26,9% | −3,8 pp, p=0,3438 |

## 🚧 Próximos Passos e Pendências
* Avaliar o tempo e o custo de estender o experimento para as 270 tarefas completas.


### Casos práticos
### Tarefa `070dd51e` — o mecanismo funcionando (e um limite do CEGIS)

A regra tem um detalhe escondido: quando linhas de cores diferentes se cruzam, a
vertical tem prioridade sobre a horizontal.

| Condição | Resultado | Chamadas |
|---|---|---|
| `sampling` | ✗ (7 tentativas, mesmo erro sempre) | 7 |
| `critic` | ✓ | 3 |
| `critic_no_oracle` | ✓ | 3 |
| `critic_cegis` | ✗ | 7 |

`critic_no_oracle` resolveu **sem nunca ver o gabarito**, só comparando código com a
regra:

> *"The code faithfully implements the stated rule by independently drawing
> horizontal and vertical line segments... overwriting grid cells where different
> colors intersect without any prioritization."*

`critic_cegis`, apesar de ver o gabarito, falhou — seu rótulo fechado
(`WRONG_TRANSFORM`) nunca conseguiu comunicar *qual* cor tem prioridade sobre qual.

### Tarefa `281123b4` — uma vitória que não prova nada

| Condição | Resultado | Chamadas | Iterações |
|---|---|---|---|
| `sampling` | ✗ | 7 | 7 |
| `critic` | ✓ | **1** | **1** |
| `critic_no_oracle` | ✓ | **1** | **1** |

`critic` e `critic_no_oracle` resolveram **na primeira geração** — nenhuma crítica foi
chamada. A primeira geração usa o mesmo prompt em todas as condições; só a
temperatura muda. Aqui a temperatura baixa acertou de primeira; a alta, mais
exploratória, errou sete vezes seguidas. **Isso não é mérito do crítico** — é lembrete
de por que a conclusão do projeto se apoia no teste pareado sobre a amostra inteira,
não em casos isolados.

