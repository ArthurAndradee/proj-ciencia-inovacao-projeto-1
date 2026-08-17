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
