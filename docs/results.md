# Resultados

Registro das rodadas. A definição das condições está em [strategies.md](strategies.md);
as escolhas de desenho, em [experimental-decisions.md](experimental-decisions.md).

## Rodada oficial — `gemini-3.5-flash-lite`, 100 tarefas

Em execução, `run-id` `official`. Reproduzir ou continuar com:

```bash
uv run arc-exp run --sample 100 --mode both --budget 7 --split evaluation \
  --workers 3 --run-id official
```

| Parâmetro | Valor |
| --- | --- |
| Modelo (ambos os papéis) | `gemini-3.5-flash-lite` |
| Split / seed | `evaluation` / 20260814 |
| Tarefas | 100 |
| `BUDGET_CALLS` | 7 (ímpar, ver decisão 6) |
| Temperatura | 0,8 (`sampling`) / 0,2 (`critic`) |

A cota do free tier (500 requisições/dia por modelo) não comporta as ~1.200 chamadas da
rodada, então ela avança ao longo de alguns dias. Como as duas condições de cada tarefa
rodam juntas, cada interrupção deixa **pares completos**, utilizáveis pela comparação
pareada. Resultados a preencher ao fim.

## Achados metodológicos das rodadas de calibração

As rodadas abaixo não entram na nota técnica como resultado, mas produziram restrições
que moldaram o desenho final. Os dados brutos foram descartados; o que ficou é o
aprendizado.

### A escolha do modelo decide o poder estatístico

O poder do teste pareado depende de haver tarefas que **uma** estratégia resolve e a
outra não. Modelos nos dois extremos destroem isso, de formas espelhadas:

| Modelo | Acurácia | Nenhuma resolve | Pares discordantes |
| --- | --- | --- | --- |
| `gemini-3.7-flash` (11 tarefas) | ~90% | ~0% | ~0 — resolve tudo na 1ª chamada |
| `gemini-3.5-flash-lite` (50 tarefas) | 26% / 28% | 66% | **7 (14%)** |
| `gemini-3.1-flash-lite` (37 tarefas) | 13,5% / 16,2% | 81% | 3 (8%) |

O modelo forte resolve na primeira geração — que é idêntica nas duas condições — e gera
só pares concordantes. O modelo fraco falha nas duas e gera pares concordantes também.
`gemini-3.5-flash-lite` é o ponto mais informativo entre os modelos alcançáveis, e é por
isso que a rodada oficial usa ele. **Não foi escolhido por conveniência de cota.**

### Modelos com raciocínio interno não controlável são inadequados

`gemma-4-26b-a4b-it` foi testado e abandonado. A partir da segunda iteração da condição
`critic`, passa a gastar **8.189 tokens pensando e 0 respondendo** — o pensamento
consome todo o `MAX_OUTPUT_TOKENS` antes de qualquer texto. Cinco chamadas consecutivas
produziram nada. A condição `sampling`, que sempre reenvia o prompt inicial, não sofre
disso: o gatilho é a **mensagem de revisão**, exatamente o que distingue a condição sob
teste.

Sem conserto: `thinking_config` responde `400 — Thinking budget is not supported for
this model`, e aumentar o teto de saída piora, porque o limite de 16.000 tokens/minuto
do Gemma já é menor que uma única chamada desta carga (~17.200 tokens). A latência
sozinha (174 s por chamada de revisão) já custaria 58 h na rodada.

**Erro de método que isso expôs:** o benchmark que aprovou o Gemma mediu 92,8 s e
`think=0` usando apenas o **prompt inicial**. O comportamento patológico só aparece nos
prompts de revisão. Avaliar um modelo para este experimento exige exercitar as duas
formas de prompt.

### O ganho do Crítico se dissolve ao descontar a primeira geração

Na rodada de 50 tarefas com `gemini-3.5-flash-lite`, o `critic` terminou +1 tarefa à
frente (14 contra 13, p = 1,0000 sobre 7 pares discordantes). Mas **5 das suas 14
vitórias vieram da primeira geração**, antes de qualquer crítica, contra 2 do
`sampling`. Essa chamada é idêntica nas duas condições em prompt e histórico; difere só
a temperatura. Descontadas, o placar atribuível ao ciclo de crítica fica **9 a 11,
favorecendo `sampling`**.

Isso não é ruído a ser eliminado: com temperaturas diferentes por definição, a primeira
amostra **faz parte** de cada estratégia. Mas a nota técnica precisa reportar o placar
com e sem esse desconto, porque a leitura muda de sinal.

### O Crítico custa o dobro em tokens pelo mesmo número de chamadas

2,56M tokens de entrada contra 1,33M do `sampling`, com 302 e 300 chamadas. O histórico
acumulado e o gabarito completo viajam a cada crítica. Por esse preço, produziu 3,52
programas por tarefa contra 6,00. **Se o orçamento fosse contado em tokens em vez de
chamadas, a comparação seria bem menos favorável ao Crítico** — ver a ameaça à validade
sobre a unidade do orçamento.

### A amostragem só converte orçamento em vantagem quando há sinal no treino

A diversidade é real: 7 de 7 programas distintos por tarefa a T=0,8. Mas em metade das
tarefas **todos** os candidatos empatam em zero pares de treino corretos — e com o
desempate pela primeira amostra, o best-of-N com orçamento 7 fica operacionalmente
idêntico a uma única tentativa. Nas tarefas difíceis do ARC o sinal de treino é fraco
demais para ranquear candidatos, que é justamente onde o Crítico tem informação que a
amostragem não tem.

### O overfit é o alvo certo e não foi convertido

Três tarefas reproduziram todos os pares de treino e erraram o teste. Nenhuma foi
resolvida pelo Crítico, apesar de serem exatamente os casos em que ver o gabarito
deveria ajudar.
