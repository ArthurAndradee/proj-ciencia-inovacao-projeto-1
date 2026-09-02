# Decisões experimentais

Registro das escolhas de desenho, com a justificativa de cada uma e o ponto do código
onde estão implementadas. São as decisões que precisam ser defendidas na nota técnica.

A definição operacional das duas condições está em [strategies.md](strategies.md).

## 1. A condição de comparação é best-of-N

**Decisão.** A estratégia contra a qual o Crítico é medido é a amostragem independente
(`sampling`): N programas gerados sem feedback, escolhendo o que reproduz mais pares de
treino.

**Por quê.** O orçamento controla **chamadas à API**, não programas. Nada obriga quem
recebe N chamadas a gastá-las revisando um único programa em série — pode gastá-las
gerando N candidatos independentes e ficando com o melhor. Medir a intervenção contra
uma alternativa que gasta o orçamento pior produziria uma vantagem que diz mais sobre o
comparativo escolhido do que sobre o método.

A escolha também muda a pergunta para melhor. Contra uma revisão sem oráculo, o
experimento responderia "qual canal de feedback conduz melhor a revisão" — uma pergunta
condicionada a *que se vá revisar*. Contra best-of-N, responde a pergunta que de fato
interessa a quem tem um orçamento para gastar: **como vale a pena gastá-lo**.

**Onde.** `runner.Condition`, `runner.solve_task`.

## 2. O que o Crítico enxerga

**Decisão.** O Crítico recebe os pares de treino **e o output do par de teste**. O
Gerador nunca vê o output do teste, em nenhuma das condições.

**Por quê.** Sem isso não haveria assimetria de informação, e a condição `critic`
viraria uma revisão comum com um passo intermediário. A assimetria precisa ser real
para que exista algo a testar: é ela que define a intervenção.

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

**Por quê.** Impedir o vazamento da resposta esperada é a restrição que sustenta a
validade da intervenção, e ela não pode depender só da boa vontade do modelo. Com o
filtro, o vazamento vira um evento mensurável: se `leak_events` for alto, o resultado da
condição `critic` fica sob suspeita e isso aparece no relatório.

**Onde.** `guards.py`, aplicado em `agents.Critic.review`.

## 6. Orçamento compartilhado

**Decisão.** Cada tarefa recebe um orçamento fixo de chamadas à API (`BUDGET_CALLS`),
e **todos** os agentes gastam dele. Em `sampling`, todas as chamadas são do Gerador;
em `critic`, cada ciclo completo custa duas.

**Por quê.** É o controle experimental que torna a comparação atribuível à estratégia:
sem ele, a condição com mais recursos venceria por ter mais recursos. Com ele, `critic`
só vence se a densidade do feedback compensar a metade dos programas produzidos.

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
diálogo — cada crítica é um julgamento independente da regra apresentada. Isso mantém o
papel restrito ao de oráculo de validação, que é o que a intervenção se propõe a testar:
um Crítico capaz de acumular raciocínio viraria um segundo solucionador.

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

## 12. Extensão da amostra para 270 tarefas

**Declarado em 20/08/2026, antes de executar a extensão.**

**Decisão.** A amostra passa de 100 para 270 tarefas de `data/evaluation`, mesma seed
(20260814). A **análise principal do experimento é a das 270 tarefas**. O resultado das
100 primeiras, já registrado em [results.md](results.md), passa a valer como **análise
interina** — descritivo, não a conclusão do estudo.

**Por quê.** Não por caça a significância. Com o efeito observado (proporção discordante
de 0,529), detectar diferença exigiria ~13.300 tarefas; nenhum N viável no split de 400
resolve isso. A extensão compra **precisão**: o intervalo de confiança de 95% para a
proporção de discordâncias passa de [0,31, 0,74] com 100 tarefas para ~[0,38, 0,66] com
270. Isto é, permite afirmar que uma eventual vantagem do crítico é **menor que ~7 pp**,
onde hoje o intervalo não descarta nem uma vantagem grande. Um resultado nulo com limite
superior estreito diz mais do que um resultado nulo sem limite algum.

**O custo estatístico, declarado.** Analisar os mesmos dados duas vezes (em 100 e em 270)
dá duas chances de cruzar α = 0,05. Simulação sob H₀ com 20.000 réplicas: a taxa de erro
tipo I sobe de 3,8% (só as 270) para 6,3% (aceitando qualquer das duas). É por isso que a
análise principal é fixada **agora** como a das 270: reportar a interina como conclusão
alternativa, caso a final não agrade, é justamente o que inflaria o erro. Se ambas forem
reivindicadas na nota, aplicar a correção de Pocock (α = 0,0294 em cada).

**Nenhuma tarefa é refeita.** Verificado que `random.sample(pool, 270)` com esta seed
contém as 100 já executadas, como prefixo idêntico — as duas amostras caem no mesmo ramo
do algoritmo do CPython (`n <= setsize`, Fisher-Yates parcial). A retomada por `task_id`
pula as 100, e apenas 170 tarefas são novas. Esta propriedade **não** é garantia da
linguagem: o que sustenta a reprodutibilidade é a lista literal de `task_ids` gravada em
`manifest.json`, não o algoritmo de amostragem.

**A hipótese principal não muda.** Continua sendo a pré-especificada desde o início: sob
orçamento fixo de chamadas, `critic` supera `sampling` em acurácia, testada por McNemar
exato sobre os pares discordantes.

**A hipótese do overfit permanece exploratória.** A observação de que o crítico produz
mais programas consistentes com o treino mas converte menos deles em acerto no teste
(23,3% contra 11,1% de overfit) nasceu da inspeção das 100 primeiras tarefas. Testá-la nos
mesmos dados que a geraram seria circular. Ela será avaliada nas **170 tarefas novas
isoladamente**, como réplica confirmatória, com a direção declarada aqui: espera-se que
`critic` apresente taxa de overfit maior que `sampling`. Poder estimado nessa réplica:
**36%** (48 programas consistentes por condição). É baixo: a réplica pode indicar se o
efeito persiste, mas a ausência de significância nela não será evidência de ausência do
efeito. Uma confirmação com poder adequado (~70%) exigiria o split inteiro, 400 tarefas.

## 13. Bug do acesso ao código — o Crítico nunca via o candidato, só a regra

**Declarado em 27/08/2026, antes de re-executar a condição `critic`.**

**O bug.** `prompts.critic_request` — a mensagem enviada ao Crítico — nunca incluiu
`proposal.code`, apenas `proposal.rule` (a regra em linguagem natural) e o relatório de
execução no treino. O Crítico julgava uma *descrição* do algoritmo, nunca o algoritmo em
si: não conseguia apontar quando o código diverge da regra enunciada, nem bugs (erro de
limite, caso de borda) visíveis só no código. A rodada oficial de 270 tarefas
(seção 12 acima, [results.md](results.md)) foi executada sob esse bug.

**Por que a correção não abre um vazamento novo.** O filtro anti-vazamento
(`guards.sanitize`, decisão 5) atua sobre a **saída** do Crítico, nunca sobre a entrada.
Dar o código ao Crítico como entrada não é informação nova nem secreta — é a própria
saída do Gerador, que o Crítico já tinha meios de reconstruir a partir da regra e do
relatório de execução, só que de forma indireta e incompleta.

**Consequência para os dados já coletados.** `critic.jsonl` da rodada oficial fica
desatualizado: o prompt que produziu aqueles dados não é mais o prompt em uso.
`sampling.jsonl` continua válido — não depende do Crítico — e é reaproveitado sem nova
execução. A condição `critic` precisa ser re-executada sob o prompt corrigido antes de
qualquer nova comparação.

**Onde.** `prompts.critic_request` (agora `critic_request(task, rule, code, result)`),
ponto de chamada em `runner.solve_task`.

## 14. Dois críticos novos: sem oráculo e contraexemplo estruturado (CEGIS)

**Declarado em 27/08/2026, antes de rodar a calibração.**

**Decisão.** Duas condições novas, paralelas e independentes — não um pipeline
sequencial único — cada uma comparada par a par contra `sampling` e contra `critic`
(corrigido):

* `critic_no_oracle` — vê os pares de treino, a regra, o código e o relatório de
  execução no treino, mas **nunca** o gabarito do par de teste. Isola: quanto do efeito
  de uma crítica estruturada vem só da estrutura, sem informação privilegiada?
* `critic_cegis` — vê o mesmo que o Crítico original (gabarito do teste incluído), mas
  em vez de até 150 palavras de prosa livre, devolve um único contraexemplo e uma classe
  de correção em vocabulário fechado (`MISSING_CASE | WRONG_TRANSFORM | WRONG_GEOMETRY |
  WRONG_COLOR_MAP | WRONG_SCOPE | OTHER`) — mais próximo de CEGIS (*Counterexample-Guided
  Inductive Synthesis*). Isola: a forma do feedback (prosa vs. contraexemplo único) muda
  o resultado, mantendo o mesmo acesso à informação?

**Por quê.** Já registrado como lacuna na seção 11, ameaça #1: *"um crítico sem acesso
ao gabarito isolaria o valor do feedback em linguagem natural; um oráculo binário
isolaria a informação da sua forma"*. Duas condições paralelas, cada uma variando um só
eixo em relação ao Crítico original, respondem a essa lacuna sem confundir as duas
variáveis numa única condição — o que aconteceria num pipeline sequencial único
(gerador → crítico sem oráculo → crítico de contraexemplo), avaliado e descartado em
favor deste desenho por não permitir atribuir o efeito a um mecanismo específico.

**Paridade de orçamento.** Ambas alternam Gerador↔Crítico exatamente como `critic` hoje
— um `critic.review()` por ciclo de revisão, sujeito ao mesmo `budget.can_afford(2)`. A
exigência de orçamento ímpar (decisão 6/7) vem desse gate compartilhado, não do tipo de
crítico, e vale para as três condições de crítico sem alteração.

**Desempate.** `prefer_latest=True` nas três condições de crítico, igual à atual — o
critério de seleção (`_better`) decide por `train_correct`, contagem objetiva da
execução, nunca pela opinião do próprio crítico sobre progresso. O que distingue o
desempate é "essa condição revisa com histórico acumulado" (as três de crítico) vs.
"essa condição reamostra do zero" (só `sampling`), não qual crítico está em uso.

**Plano de comparações pré-registrado, com correção de Bonferroni.**

| # | Par | Isola |
|---|-----|-------|
| 1 | `sampling` vs `critic` | hipótese original, re-testada com o bug corrigido |
| 2 | `sampling` vs `critic_no_oracle` | valor da crítica estruturada sem oráculo |
| 3 | `sampling` vs `critic_cegis` | valor do oráculo em forma de contraexemplo único |
| 4 | `critic` vs `critic_no_oracle` | valor do acesso ao gabarito, mantendo a forma prosa |
| 5 | `critic` vs `critic_cegis` | valor da forma estruturada, mantendo o acesso ao gabarito |

`critic_no_oracle` vs `critic_cegis` fica fora da família pré-registrada — varia acesso
ao gabarito e forma do feedback ao mesmo tempo, confundido — e só é reportado como
exploratório se aparecer. 5 comparações pré-registradas ⇒ **Bonferroni, α = 0,05/5 =
0,01** por teste. Distinto da correção de Pocock já usada na seção 12: Pocock corrige
múltiplas *olhadas no tempo* sobre os mesmos dados (100 depois 270 tarefas); Bonferroni
aqui corrige múltiplas comparações *simultâneas* sobre o mesmo conjunto de dados.

**Escala.** Calibração pequena primeiro (~30-50 tarefas), antes de comprometer a escala
de 270 usada na rodada oficial — mesmo padrão já seguido em `calibracao.md` antes da
rodada oficial de 100/270. A decisão de estender fica condicionada ao que a calibração
mostrar.

**Onde.** `runner.Condition.CRITIC_NO_ORACLE`/`CRITIC_CEGIS`, `runner.CriticSpec`/
`CRITIC_SPECS`, `prompts.CRITIC_NO_ORACLE_SYSTEM`/`CRITIC_CEGIS_SYSTEM`,
`prompts.critic_request_no_oracle`/`critic_request_cegis`,
`report.PRIMARY_COMPARISONS`.

## 15. Bug de encoding — leitura/escrita de texto assumia o encoding da plataforma

**Descoberto em 28/08/2026, ao tentar retomar a rodada de 270 tarefas num ambiente
Windows.**

**O bug.** `Path.read_text()`, `Path.write_text()` e `open(path, "a")`, em
`experiment.py`, `cli.py`, `metrics.py`, `dataset.py`, `executor.py` e
`_sandbox_child.py`, nunca declaravam `encoding="utf-8"` — usavam o encoding padrão da
plataforma (`locale.getpreferredencoding()`). No macOS onde o projeto foi desenvolvido
isso é UTF-8 por padrão, então o bug nunca apareceu. No Windows, o padrão é a *code page*
do sistema (cp1252 em máquinas em português/inglês), que não consegue representar vários
bytes que aparecem rotineiramente em texto gerado pelo Gemini (travessões, aspas
tipográficas). O sintoma: `UnicodeDecodeError` ao tentar **retomar** uma rodada (ler de
volta um `.jsonl` já escrito), o que interrompe a execução antes mesmo de processar a
primeira tarefa pendente — não é um erro cosmético, impede qualquer rodada real num
ambiente Windows assim que o conteúdo gerado pelo modelo contém um caractere fora do
cp1252.

**Por que não é uma mudança de comportamento.** UTF-8 explícito é estritamente mais
correto do que depender do locale da máquina que roda o comando — é o mesmo texto, só
decodificado/codificado de um jeito que não depende de em qual sistema operacional o
comando roda. Arquivos já escritos por uma rodada anterior em UTF-8 (como
`results/runs/official/*.jsonl`, gerados em macOS) continuam legíveis sem conversão.

**Onde.** Todos os `read_text`/`write_text`/`open` de arquivo texto em
`src/arc_experiment/` passaram a declarar `encoding="utf-8"` explicitamente. Teste de
regressão: `test_resuming_a_run_with_non_ascii_output_does_not_crash` em
`tests/test_experiment.py`.
