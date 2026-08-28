# Roteiro da apresentação

> Conteúdo slide a slide. Cada bloco = um slide. "Fala" é sugestão de texto oral, não
> pra colar no slide. Visual sugere o que desenhar/mostrar.

## 1. Título

**Slide**: título do projeto, ARC-AGI-1, nomes da equipe, data.

## 2. A pergunta

**Slide**: "Dado um orçamento fixo de chamadas a um LLM, é melhor **diversificar**
(N tentativas independentes) ou **iterar** (uma tentativa revisada por um crítico)?"

**Fala**: situar o ARC-AGI-1 em uma frase (grades de entrada/saída, inferir a regra),
depois a pergunta orientadora do projeto.

## 3. A arquitetura base — dois agentes

**Visual**: diagrama Gerador → Executor (sandbox) → (Crítico, se aplicável).

**Slide**:
- Gerador: vê treino + entrada de teste, propõe regra + código. Nunca vê a saída do teste.
- Crítico: só dá feedback em prosa, nunca escreve código, nunca propõe solução.

## 4. As quatro condições

**Visual**: tabela (a mesma do relatório — condição / o que vê / custo por ciclo).

**Fala**: enfatizar que todas competem sob o mesmo orçamento de chamadas — essa é a
regra que torna a comparação justa.

## 5. O bug encontrado

**Slide**: trecho de código antes/depois de `critic_request` (a assinatura sem/com
`code`).

**Fala**: "Auditando por que a rodada original deu resultado nulo, achamos que o Crítico
nunca via o código — só a regra em português. Ele julgava uma *descrição* do algoritmo,
nunca o algoritmo em si." Mostrar a citação real da crítica pós-correção
("the code implements a simpler neighborhood check...").

## 6. Por que dois críticos novos

**Visual**: diagrama de 2 eixos — acesso ao gabarito (sim/não) × forma do feedback
(prosa livre/estruturada).

```
                    prosa livre          estruturada
acesso ao gabarito     critic             critic_cegis
sem acesso          critic_no_oracle          —
```

**Fala**: o resultado nulo original não dizia *por quê* — faltava acesso ao gabarito
importar menos do que se pensava, ou a forma do feedback não ser a mais eficaz? Cada
crítico novo isola um eixo.

## 7. O ciclo de uma tarefa

**Visual**: o fluxograma do pipeline (Gerador → Executor → critério de parada → Crítico
→ filtro anti-vazamento → de volta ao Gerador).

**Fala**: destacar a regra de ouro — o gabarito do teste **nunca decide nada**, só mede
no final. Se decidisse, a taxa de acerto viraria um "limite superior de oráculo".

## 8. Como medimos "melhor"

**Slide**:
- Desenho pareado (mesmas tarefas, mesmo orçamento, nas 4 condições)
- McNemar exato sobre as discordâncias
- 5 comparações pré-registradas + correção de Bonferroni (α = 0,01)

**Fala**: por que pareado (controla ruído entre tarefas) e por que pré-registrar as
comparações (evita "caçar" um resultado significativo depois de ver os dados).

## 9. Resultado

**Visual**: tabela de acurácia + tabela de p-valores (as duas de `docs/results.md`
Parte A).

**Fala**: nenhuma das 5 comparações é significativa. A mais próxima (`critic` vs
`critic_cegis`, p=0,0391) pareceria significativa isolada, mas não sobrevive à correção
para 5 comparações simultâneas — importante deixar isso explícito, é fácil de errar.

## 10. A direção inverteu — e isso é o achado

**Visual**: gráfico de barras simples comparando acurácia na calibração (n=30) vs na
rodada final (n=60) — mostrando a inversão de sinal para `critic`.

**Fala**: na calibração, `critic` corrigido ficava abaixo de `sampling`; na rodada
final, ficou acima — sem nenhuma das duas ser significativa. Isso não é uma
contradição, é evidência de que amostras pequenas (30 ou 60 tarefas) têm variância
grande demais pra revelar direção com confiança. Conecta com o motivo de a rodada
original ter precisado de 270 tarefas.

## 11. Exemplo qualitativo — o mecanismo funcionando

**Visual**: o Caso 1 de `docs/exemplo-execucao-criticos-novos.md` (tarefa `070dd51e`) —
mostrar a tabela de resultado por condição + a citação da crítica do `critic_no_oracle`.

**Fala**: contar a história — `sampling` erra 7 vezes do mesmo jeito; `critic_no_oracle`
resolve em 2 rodadas **sem ver o gabarito**, só comparando código com a regra;
`critic_cegis` falha porque o rótulo fechado não consegue dizer "vertical tem
prioridade sobre horizontal".

## 12. Exemplo qualitativo — uma armadilha metodológica

**Visual**: o Caso 2 (tarefa `281123b4`) — `critic` e `critic_no_oracle` resolvem em 1
chamada só (primeira geração, sem crítica nenhuma).

**Fala**: nem toda vitória é mérito do crítico — aqui foi só a temperatura mais baixa
acertando de primeira. É por isso que a conclusão do projeto se apoia no teste
estatístico sobre a amostra inteira, não em casos isolados.

## 13. Limitações, declaradas

**Slide** (lista curta, direta):
- Escala menor que a rodada original (60 tarefas vs 270) — poder estatístico baixo
- 3 das 9 chaves de API com problema de credencial — reduziu capacidade disponível
- Execução única por tarefa — parte da variação é ruído do próprio modelo

## 14. Conclusão e próximo passo

**Slide**:
- Bug real corrigido e validado
- Dois críticos novos implementados e testados, isolando duas hipóteses distintas
- Nenhum efeito significativo encontrado — consistente com o resultado nulo original
- Próximo experimento que os resultados justificam: estender para a mesma escala de 270
  tarefas da rodada original, com poder estatístico suficiente para confirmar (ou não) a
  direção observada aqui

## 15. Perguntas

**Slide**: obrigado + link do repositório.
