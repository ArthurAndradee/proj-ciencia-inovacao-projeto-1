# proj-ciencia-inovacao-projeto-1


<h2>14/08/2026 - 11:35</h2>

Foi definido:
- Escopo
- Definição
- Hipóteses
  
<h3>Definição do projeto:</h3>

O experimento avaliará a síntese por LLMs de programas para o ARC-AGI-1, contrapondo um baseline de self-debugging a uma intervenção multi-agente baseada em feedback. 
A hipótese central é que a introdução de um Agente Crítico com acesso exclusivo ao gabarito da tarefa aumentará a taxa de acertos sob um orçamento fixo de requisições à API. 

O diferencial arquitetônico desta intervenção é que o Agente Crítico não propõe soluções, sendo sua função unicamente comparar a explicação lógica gerada pelo primeiro agente com o gabarito, retornando um feedback estruturado em linguagem natural que aponta exclusivamente as contradições na resposta dada. Isso garante que o modelo gerador corrija seu próprio raciocínio a partir da identificação de falhas e contraexemplos, sem que ocorra vazamento da resposta esperada. 

Para garantir a validade científica e a atribuição correta da diferença observada, a execução manterá o mesmo limite total de chamadas à API, testando se a alta densidade informacional desse feedback restritivo compensa a inevitável redução no número de iterações de código. A documentação consolidada no repositório Git e na nota técnica seguirá um padrão estritamente técnico e reprodutível, detalhando as configurações de isolamento de escopo dos prompts e analisando sistematicamente os casos em que essa validação por oposição ajudou ou prejudicou o desempenho.  

<h2>28/08/2026</h2>

Foi definido/feito:
- Correção de um bug real no Agente Crítico
- Dois críticos novos, para isolar as causas de um efeito que a rodada de 270 tarefas não tinha conseguido explicar
- Rodada nova de 60 tarefas, comparando as quatro condições

<h3>O bug encontrado</h3>

Auditando o fluxo de dados do Crítico (não uma correção pedida de antemão — foi encontrada ao investigar por que a rodada oficial de 270 tarefas não confirmou a hipótese), constatou-se que `prompts.critic_request` nunca recebia o código candidato do Gerador, só a regra em linguagem natural e o placar de acerto no treino. O Crítico julgava uma descrição do algoritmo, nunca o algoritmo em si. Corrigido; a mudança não abre vazamento novo (o filtro anti-vazamento continua atuando sobre a saída do Crítico, não sobre a entrada) e foi validada inspecionando críticas reais, que passaram a citar o comportamento do código explicitamente — algo impossível antes.

<h3>Os dois críticos novos</h3>

Fundamentados numa lacuna que a própria seção de ameaças à validade da rodada de 270 tarefas já registrava: o resultado nulo original não permitia dizer *por que* o Crítico não ajudou — se por falta de acesso ao gabarito importar menos do que se pensava, ou por a forma livre do feedback não ser a mais eficaz. `critic_no_oracle` isola a primeira pergunta (revisa código e regra, nunca vê o gabarito do teste); `critic_cegis` isola a segunda (mantém o acesso ao gabarito, mas responde num vocabulário fechado — um contraexemplo e uma classe de correção — em vez de prosa livre, no espírito de CEGIS).

<h3>O resultado da rodada de 60 tarefas</h3>

Nenhuma das 5 comparações pré-registradas (`sampling` vs cada crítico, `critic` vs os dois novos) é estatisticamente significativa sob a correção de Bonferroni para múltiplas comparações. A direção observada (crítico corrigido acima de `sampling`) inverteu frente a uma calibração menor de 30 tarefas — sinal de que ambas as leituras são ruído de amostra pequena, não um efeito real. Consistente com o resultado nulo já visto na rodada de 270 tarefas. Detalhes completos, com intervalos de confiança e exemplos qualitativos de acerto/falha, em `docs/results.md` e `docs/exemplo-execucao-criticos-novos.md`.

<h3>Uso de IA nesta sessão — registro proporcional</h3>

> **A preencher.** Esta sessão foi conduzida com assistência intensiva de IA (Claude Code) — desde a investigação do bug até a implementação, execução dos experimentos e escrita da documentação. O registro proporcional exigido pela especificação do projeto (§6) é uma autoavaliação da equipe sobre o próprio envolvimento no trabalho, não algo que a própria IA deva preencher. Fica pendente de complementação por quem conduziu a sessão, descrevendo concretamente: quais decisões foram tomadas/revisadas por humanos (ex.: a escolha de arquitetura dos críticos foi apresentada como pergunta explícita e decidida pela equipe, não pela IA), o que foi aceito sem alteração, e o que foi verificado manualmente (ex.: leitura das críticas brutas, conferência dos p-valores).
