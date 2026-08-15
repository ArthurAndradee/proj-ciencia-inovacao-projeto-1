# Decisões experimentais

Registro das escolhas de desenho que o `README.md` não fixa, com a justificativa de
cada uma e o ponto do código onde estão implementadas. São as decisões que precisam
ser defendidas na nota técnica.

## 1. O que o Crítico enxerga

**Decisão.** O Crítico recebe os pares de treino **e o output do par de teste**. O
Gerador nunca vê o output do teste, em nenhuma das condições.

**Por quê.** Se o Crítico visse apenas os pares de treino, não haveria assimetria de
informação: o Gerador já os tem, e a intervenção viraria o baseline com um passo
intermediário. A assimetria precisa ser real para que o experimento teste o que o
README propõe.

**Onde.** `prompts.generator_initial` monta a mensagem do Gerador apenas com treino +
input do teste; `prompts.critic_request` inclui o output do teste. O teste
`test_critic_prompt_contains_the_ground_truth_but_generator_prompt_does_not` trava
essa separação.

## 2. O gabarito do teste não decide nada

**Decisão.** O critério de parada é idêntico nas duas condições: o candidato é aceito
quando reproduz **todos os pares de treino**. O candidato final é o melhor pelos pares
de treino, com desempate pela iteração mais recente. O par de teste é executado uma
única vez, ao final, apenas para medir.

**Por quê.** É a salvaguarda que separa duas coisas facilmente confundidas: usar o
gabarito para *formular feedback* e usar o gabarito para *selecionar a resposta*. Se o
laço parasse quando o código acertasse o teste, a taxa de acerto viraria um limite
superior de oráculo, não uma medida de desempenho. Com essa restrição, o oráculo
influencia o raciocínio do Gerador, mas nunca escolhe por ele.

**Onde.** `runner.solve_task` — `_better` compara apenas `train_correct`, e
`run_code(best.code, [task.test_pair])` só é chamado depois que o laço termina.

## 3. Filtro anti-vazamento

**Decisão.** O feedback do Crítico passa por `guards.sanitize` antes de chegar ao
Gerador. São redigidas linhas compostas só de inteiros (grades, listas de coordenadas)
e qualquer código — blocos cercados ou linhas com `def`, `import`, `return`, `for`,
`while`. A resposta bruta é preservada no JSONL para auditoria, e cada redação é
contada em `leak_events`.

**Por quê.** A restrição arquitetônica do README ("evitar o vazamento da resposta
esperada") não pode depender só da boa vontade do modelo. Com o filtro, o vazamento
vira um evento mensurável: se `leak_events` for alto, o resultado da intervenção fica
sob suspeita e isso aparece no relatório.

**Onde.** `guards.py`, aplicado em `agents.Critic.review`.

## 4. Orçamento compartilhado

**Decisão.** Cada tarefa recebe um orçamento fixo de chamadas à API (`BUDGET_CALLS`),
e **todos** os agentes gastam dele. No baseline, todas as chamadas são do Gerador; na
intervenção, cada ciclo completo custa duas (Gerador + Crítico).

**Por quê.** É o controle experimental exigido pelo README: sem ele, a intervenção
teria mais recursos que o baseline e a diferença observada não seria atribuível à
arquitetura. Com ele, a intervenção só vence se a densidade do feedback compensar a
metade das iterações.

**Onde.** `llm.Budget`, instanciado uma vez por tarefa em `runner.solve_task` e
compartilhado por `Generator` e `Critic`. O teste
`test_intervention_gets_fewer_iterations_under_the_same_budget` documenta a troca.

**Detalhe.** A intervenção só chama o Crítico se ainda couberem duas chamadas, para
não terminar o orçamento em um feedback que ninguém poderá usar. Logo, a última
chamada de uma tarefa é sempre do Gerador.

## 5. Crítico sem memória

**Decisão.** O Crítico é reinstanciado em cada rodada: recebe a regra atual e o
gabarito, sem histórico das rodadas anteriores. O Gerador, ao contrário, mantém o
histórico completo da conversa.

**Por quê.** Sem memória, o Crítico não consegue construir uma solução ao longo do
diálogo — cada crítica é um julgamento independente da regra apresentada. Isso mantém
o papel restrito a oráculo de validação, como o README exige.

**Onde.** `agents.Critic.review` monta a lista de mensagens do zero a cada chamada.

## 6. Amostra e estatística

**Decisão.** 100 tarefas sorteadas de `data/evaluation` com seed fixa; as duas
condições rodam sobre as mesmas tarefas. A comparação usa o teste de McNemar exato
sobre os pares discordantes.

**Por quê.** O desenho é pareado por construção (mesmas tarefas, mesmo orçamento),
então um teste pareado é o correto: o que importa não é a diferença de acurácia bruta,
mas quantas tarefas cada condição resolveu que a outra não. A versão exata (binomial)
evita a aproximação qui-quadrado, ruim com poucas discordâncias — o cenário provável
em uma amostra de 100 tarefas num benchmark difícil.

**Onde.** `metrics.exact_mcnemar_p` e `metrics.compare`.

## 7. Modelos

**Decisão.** Gemini via Google AI Studio, mesmo modelo nos dois papéis
(`GENERATOR_MODEL` e `CRITIC_MODEL` no `.env`), temperatura baixa.

**Por quê.** Usar o mesmo modelo nos dois papéis isola a variável arquitetural. Se o
Crítico fosse um modelo diferente, uma eventual vantagem da intervenção poderia ser
atribuída à capacidade do segundo modelo, não à assimetria de informação. Temperatura
baixa reduz a variância entre condições, já que cada tarefa roda uma única vez.

## 8. Ameaças à validade

1. **O oráculo não é autônomo.** A intervenção usa informação indisponível em um
   cenário real de resolução do ARC. O número reportado mede o valor da validação por
   oposição, não um sistema utilizável em produção. Isso precisa estar explícito na
   nota técnica.
2. **Duas variáveis ainda confundidas.** A intervenção altera simultaneamente o
   *acesso ao gabarito* e a *forma do feedback* (linguagem natural estruturada). A
   condição C descrita no plano de implementação separaria as duas.
3. **Execução única por tarefa.** Sem repetições, parte da diferença observada pode
   ser ruído de amostragem do modelo. Mitigado pela temperatura baixa e pelo
   pareamento, não eliminado.
4. **Vazamento residual.** O filtro pega grades e código, não paráfrases ("a saída tem
   metade da altura"). `leak_events` mede o que foi barrado, não o que passou; a
   leitura manual dos feedbacks brutos nos casos discordantes é parte da análise.
5. **Erros de API contam como falha.** Uma tarefa interrompida por erro após as
   tentativas de retry é registrada com `stop_reason = api_error` e conta como não
   resolvida. Se forem frequentes, a rodada deve ser repetida — o campo `api_errors`
   do relatório existe para tornar isso visível.
