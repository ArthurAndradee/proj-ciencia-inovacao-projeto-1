# Decisões experimentais

Registro das escolhas de desenho que o `README.md` não fixa, com a justificativa de
cada uma e o ponto do código onde estão implementadas. São as decisões que precisam
ser defendidas na nota técnica.

A definição operacional das duas condições está em [strategies.md](strategies.md).

## 1. O baseline é best-of-N, não self-debugging

**Decisão.** A condição de comparação é a amostragem independente (`sampling`), não o
self-debugging que o `README.md` menciona.

**Por quê.** O orçamento controla **chamadas à API**, não programas. Nada obriga quem
recebe N chamadas a gastá-las revisando um único programa em série: pode gastá-las
gerando N programas independentes e ficando com o melhor pelos pares de treino. Essa
estratégia é conhecidamente competitiva em síntese de programa. Comparar a
intervenção contra o self-debugging responderia "qual canal de feedback conduz melhor
a revisão", uma pergunta condicionada a *que se vá revisar*; comparar contra best-of-N
responde a pergunta que interessa: **como vale a pena gastar o orçamento**.

**Custo.** O texto original do `README.md` deixa de descrever o experimento executado.
O README não foi alterado; este documento registra o desvio, que precisa aparecer na
nota técnica.

**Onde.** `runner.Condition`, `runner.solve_task`.

## 2. O que o Crítico enxerga

**Decisão.** O Crítico recebe os pares de treino **e o output do par de teste**. O
Gerador nunca vê o output do teste, em nenhuma das condições.

**Por quê.** Sem isso não haveria assimetria de informação, e a condição `critic`
viraria uma revisão comum com um passo intermediário. A assimetria precisa ser real
para que o experimento teste o que o README propõe.

**Onde.** `prompts.generator_initial` monta a mensagem do Gerador apenas com treino +
input do teste; `prompts.critic_request` inclui o output do teste. O teste
`test_critic_prompt_contains_the_ground_truth_but_generator_prompt_does_not` trava
essa separação.

## 3. O gabarito do teste não decide nada

**Decisão.** O critério de parada é idêntico nas duas condições: o candidato é aceito
quando reproduz **todos os pares de treino**. O candidato final é o melhor pelos pares
de treino. O par de teste é executado uma única vez, ao final, apenas para medir.

**Por quê.** É a salvaguarda que separa duas coisas facilmente confundidas: usar o
gabarito para *formular feedback* e usar o gabarito para *selecionar a resposta*. Se o
laço parasse quando o código acertasse o teste, a taxa de acerto viraria um limite
superior de oráculo, não uma medida de desempenho.

**Onde.** `runner.solve_task` — `_better` compara apenas `train_correct`, e
`run_code(best.code, [task.test_pair])` só é chamado depois que o laço termina.

## 4. Desempate por condição

**Decisão.** Empates na consistência com o treino ficam com a **última** iteração em
`critic` e com a **primeira** amostra em `sampling`.

**Por quê.** Em `critic` a iteração mais recente incorporou feedback, então preferi-la
é coerente com a estratégia. Em `sampling` não há progressão: a sétima amostra não é a
priori melhor que a primeira. Manter `>=` ali faria com que amostrar mais deslocasse a
escolha por si só, dando à estratégia uma vantagem que não vem da qualidade dos
candidatos.

**Onde.** `runner._better`, parâmetro `prefer_latest`.

## 5. Filtro anti-vazamento

**Decisão.** O feedback do Crítico passa por `guards.sanitize` antes de chegar ao
Gerador. São redigidas linhas compostas só de inteiros (grades, listas de coordenadas)
e qualquer código — blocos cercados ou linhas com `def`, `import`, `return`, `for`,
`while`. A resposta bruta é preservada no JSONL para auditoria, e cada redação é
contada em `leak_events`.

**Por quê.** A restrição arquitetônica do README ("evitar o vazamento da resposta
esperada") não pode depender só da boa vontade do modelo. Com o filtro, o vazamento
vira um evento mensurável: se `leak_events` for alto, o resultado da condição `critic`
fica sob suspeita e isso aparece no relatório.

**Onde.** `guards.py`, aplicado em `agents.Critic.review`.

## 6. Orçamento compartilhado

**Decisão.** Cada tarefa recebe um orçamento fixo de chamadas à API (`BUDGET_CALLS`),
e **todos** os agentes gastam dele. Em `sampling`, todas as chamadas são do Gerador;
em `critic`, cada ciclo completo custa duas.

**Por quê.** É o controle experimental exigido pelo README: sem ele, a comparação não
seria atribuível à estratégia. Com ele, `critic` só vence se a densidade do feedback
compensar a metade dos programas produzidos.

**Onde.** `llm.Budget`, instanciado uma vez por tarefa em `runner.solve_task` e
compartilhado por `Generator` e `Critic`. O teste
`test_critic_condition_buys_fewer_iterations_with_the_same_budget` documenta a troca.

**Detalhe.** `critic` só chama o Crítico se ainda couberem duas chamadas, para não
terminar o orçamento em um feedback que ninguém poderá usar. Logo, a última chamada de
uma tarefa é sempre do Gerador, e **o orçamento deve ser ímpar**: com `BUDGET_CALLS=6`
a condição usaria 5 chamadas enquanto `sampling` usaria 6.

## 7. Temperaturas diferentes

**Decisão.** `sampling` roda a 0.8 e `critic` a 0.2.

**Por quê.** Amostragem sem diversidade não é amostragem. Com 0.2 nas duas, as N
amostras tendem a colapsar em quase o mesmo programa e o best-of-N vira uma tentativa
repetida N vezes — um espantalho, e a comparação perderia o sentido.

**Custo metodológico.** A temperatura passa a ser mais um eixo de diferença entre as
condições. Ele é constitutivo da estratégia, não uma variável de nuisance, mas
precisa ser declarado: parte de uma eventual vantagem de `sampling` vem de explorar um
espaço maior, e isso é a estratégia funcionando, não um artefato.

**Onde.** `config.sampling_temperature`, `experiment.temperature_for`,
`llm.LLMClient.generate(temperature=...)`.

## 8. Crítico sem memória

**Decisão.** O Crítico é reinstanciado em cada rodada: recebe a regra atual e o
gabarito, sem histórico das rodadas anteriores. O Gerador, ao contrário, mantém o
histórico completo da conversa.

**Por quê.** Sem memória, o Crítico não consegue construir uma solução ao longo do
diálogo — cada crítica é um julgamento independente da regra apresentada. Isso mantém
o papel restrito a oráculo de validação, como o README exige.

**Onde.** `agents.Critic.review` monta a lista de mensagens do zero a cada chamada.

## 9. Amostra e estatística

**Decisão.** 100 tarefas sorteadas de `data/evaluation` com seed fixa; as duas
condições rodam sobre as mesmas tarefas. A comparação usa o teste de McNemar exato
sobre os pares discordantes.

**Por quê.** O desenho é pareado por construção (mesmas tarefas, mesmo orçamento),
então um teste pareado é o correto: o que importa não é a diferença de acurácia bruta,
mas quantas tarefas cada condição resolveu que a outra não. A versão exata (binomial)
evita a aproximação qui-quadrado, ruim com poucas discordâncias.

**Por que 100 e não menos.** Uma rodada piloto de calibração (30 tarefas, orçamento 6)
mediu uma taxa de discordância de ~17%. Extrapolando, e considerando a divisão mais
equilibrada dos pares discordantes que ainda atinge p < 0,05 pelo McNemar exato:

| Tarefas | Discordantes esperados | Divisão necessária |
| --- | --- | --- |
| 30 | ~5 | **impossível** — nem 0×5 (p = 0,0625) cruza 0,05 |
| 100 | ~17 | 4×13 ou mais desequilibrada |
| 200 | ~34 | 10×24 ou mais desequilibrada |

Cem tarefas é o mínimo para o teste ter alguma chance, e exige que a condição vencedora
leve ~76% das discordâncias.

**Onde.** `metrics.exact_mcnemar_p` e `metrics.compare`.

## 10. Modelos

**Decisão.** Gemini via Google AI Studio, mesmo modelo nos dois papéis
(`GENERATOR_MODEL` e `CRITIC_MODEL` no `.env`).

**Por quê.** Usar o mesmo modelo nos dois papéis isola a variável arquitetural. Se o
Crítico fosse um modelo diferente, uma eventual vantagem de `critic` poderia ser
atribuída à capacidade do segundo modelo, não à assimetria de informação.

**Nota prática.** No free tier a cota é **por modelo**, e os modelos `flash-lite` têm
cota bem maior que os `flash`. O modelo efetivamente usado precisa ser registrado na
nota técnica: a taxa de acerto absoluta depende fortemente dele.

## 11. Ameaças à validade

1. **Confundimento múltiplo.** `sampling` e `critic` diferem em quatro eixos ao mesmo
   tempo: existência de feedback, acesso ao gabarito, orçamento em paralelo ou em
   série, e temperatura. Um resultado positivo sustenta a leitura pragmática ("gastar
   o orçamento assim rende mais acertos") e **não** a causal ("a assimetria de
   informação é o que funciona"). Separar as causas exigiria condições adicionais —
   um crítico sem acesso ao gabarito isolaria o valor do feedback em linguagem
   natural; um oráculo binário isolaria a informação da sua forma.
2. **O oráculo não é autônomo.** A condição `critic` usa informação indisponível em um
   cenário real de resolução do ARC. O número reportado mede o valor da validação por
   oposição, não um sistema utilizável em produção.
3. **Execução única por tarefa.** Sem repetições, parte da diferença observada é ruído
   de amostragem do modelo — e em `sampling`, por construção, a temperatura alta
   aumenta essa variância. Mitigado pelo pareamento, não eliminado.
4. **Vazamento residual.** O filtro pega grades e código, não paráfrases ("a saída tem
   metade da altura"). `leak_events` mede o que foi barrado, não o que passou; a
   leitura manual dos feedbacks brutos nos casos discordantes é parte da análise.
5. **Erros de API.** Uma tarefa interrompida por erro após as tentativas de retry é
   registrada com `stop_reason = api_error` e **excluída da comparação pareada** — um
   modelo indisponível não é evidência sobre o método, e contá-la como falha daria à
   outra condição um par discordante que ela não conquistou. O relatório informa
   quantas tarefas saíram por esse motivo; se forem muitas, a rodada deve ser repetida.
