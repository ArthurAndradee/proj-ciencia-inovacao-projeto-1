# Críticos para ARC-AGI-1 — Apresentação do Projeto

> Este documento **é** a apresentação — sem slides. Pensado pra ser lido de cima a
> baixo em voz alta, com as seções de perguntas servindo de apoio pra defesa oral.

**Equipe** · `proj-ciencia-inovacao-projeto-1` · ARC-AGI-1 · Projeto em Ciência e Inovação

---

## Sumário

- [1. A pergunta orientadora](#1-a-pergunta-orientadora)
- [2. Como o experimento é estruturado](#2-como-o-experimento-é-estruturado)
- [3. O que já existia antes desta etapa](#3-o-que-já-existia-antes-desta-etapa)
- [4. O bug que encontramos](#4-o-bug-que-encontramos)
- [5. Os dois críticos novos](#5-os-dois-críticos-novos)
- [6. Resultados](#6-resultados)
- [7. Exemplos reais — quando funcionou e quando não](#7-exemplos-reais--quando-funcionou-e-quando-não)
- [8. Limitações, declaradas](#8-limitações-declaradas)
- [9. Conclusão e próximo passo](#9-conclusão-e-próximo-passo)
- [10. Perguntas e respostas antecipadas](#10-perguntas-e-respostas-antecipadas)

---

## 1. A pergunta orientadora

> Dado um **orçamento fixo de chamadas a um LLM**, é melhor gastar esse orçamento
> **diversificando** (várias tentativas independentes) ou **iterando** (uma tentativa
> revisada por um Agente Crítico)?

O ARC-AGI-1 dá tarefas de raciocínio abstrato: pares de grades entrada→saída (o
**treino**) que compartilham uma transformação, e uma entrada de teste cuja saída (o
**gabarito**) fica escondida. Resolver = inferir a regra e escrever um programa Python
que a implemente e generalize.

---

## 2. Como o experimento é estruturado

### Os dois papéis

- **Gerador** — vê o treino e a entrada de teste, propõe uma regra em prosa e um
  programa `transform(grid)`. **Nunca** vê a saída do teste, em nenhuma condição.
- **Crítico** — só dá feedback (prosa ou rótulo fechado, conforme a variante). Nunca
  escreve código, nunca propõe solução — isso é imposto pelo prompt de sistema **e**
  por um filtro automático que redige qualquer código/grade que escape na resposta.

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

**Regra de ouro do desenho:** o gabarito do teste **nunca decide nada** — só é usado
uma vez, no fim, pra medir se o candidato final acertou. Se decidisse, a taxa de
acerto viraria um "limite superior de oráculo", não uma medida real de desempenho.

### As quatro condições comparadas

Todas competem sob o **mesmo orçamento de chamadas por tarefa** — é essa restrição
compartilhada que torna a comparação justa.

| Condição | O que o Crítico vê | Forma da resposta | Custo/ciclo |
|---|---|---|---|
| `sampling` | — (sem Crítico) — | — | 1 chamada |
| `critic` | código + regra + **gabarito do teste** | prosa livre (≤150 palavras) | 2 chamadas |
| `critic_no_oracle` | código + regra + treino *(sem gabarito)* | prosa livre | 2 chamadas |
| `critic_cegis` | código + regra + **gabarito do teste** | 1 contraexemplo + 1 rótulo fechado | 2 chamadas |

`sampling` gera N tentativas independentes (conversa nova a cada vez, temperatura
alta pra diversificar) e fica com a que acerta mais pares de treino. As condições de
crítico gastam metade das chamadas em revisão guiada — por isso produzem menos
programas com o mesmo orçamento.

---

## 3. O que já existia antes desta etapa

| Data | O que foi feito |
|---|---|
| 14/08 | Escopo definido: comparar `sampling` contra um Agente Crítico com acesso ao gabarito, sob orçamento fixo |
| 15–21/08 | Pipeline construído (Gerador, Executor, Crítico, filtro anti-vazamento). 12 decisões de desenho documentadas e justificadas |
| 21/08 | **Rodada oficial: 270 tarefas.** `sampling` 32,6% vs `critic` 31,9%. McNemar exato **p = 0,8877**. IC 95%: [−5,6 pp, +4,3 pp] |

**Achado adicional daquela rodada:** metade das vitórias de cada condição vinha da
**primeira geração** — idêntica nas duas, só a temperatura muda. Descontando-a, o
placar ficava 44 a 44. O modelo usado, `gemini-3.5-flash-lite`, foi escolhido por
calibração (é o único, entre os testados, que gerou discordâncias suficientes pro
teste pareado ter poder estatístico) — não por conveniência de cota.

> A hipótese original não se confirmou. Um resultado nulo bem medido — com intervalo
> de confiança que diz **quanto** uma vantagem não pode ser — já é uma resposta válida
> à pergunta orientadora. Foi esse resultado que motivou a investigação que segue.

---

## 4. O bug que encontramos

Investigando por que o resultado deu nulo, auditamos o fluxo de dados do Crítico —
não foi uma correção pedida de antemão.

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

**Por que a correção não abre vazamento novo:** o filtro anti-vazamento age sobre a
**saída** do Crítico, nunca sobre a entrada — e o código do Gerador não é informação
secreta, é a própria saída do Gerador.

**Como confirmamos que funciona de verdade** (não só que compila): inspecionamos
críticas reais, brutas. Depois da correção aparecem trechos como:

> *"The code implements a simpler neighborhood check for any cell adjacent to both a 4
> and a 5, converting many incorrect cells while missing the true pattern
> requirement..."*

Uma crítica sobre o que o **código faz**, não sobre o que a regra diz — estruturalmente
impossível antes.

---

## 5. Os dois críticos novos

O resultado nulo original não dizia **por quê** — faltava acesso ao gabarito importar
menos do que se pensava, ou a forma livre do feedback não ser a mais eficaz? Cada
crítico novo isola um desses dois eixos:

|  | Vê o gabarito? | Forma da resposta |
|---|:---:|---|
| `critic` (original, corrigido) | ✅ | prosa livre |
| `critic_no_oracle` | ❌ | prosa livre |
| `critic_cegis` | ✅ | contraexemplo + rótulo fechado |

`critic_cegis` responde só com um dos seis rótulos: `MISSING_CASE`,
`WRONG_TRANSFORM`, `WRONG_GEOMETRY`, `WRONG_COLOR_MAP`, `WRONG_SCOPE`, `OTHER` — no
espírito de **CEGIS** (*Counterexample-Guided Inductive Synthesis*, citado na própria
especificação do projeto).

**Decisão de arquitetura:** os dois críticos rodam como **condições paralelas**, não
como um pipeline sequencial (gerador → crítico 1 → crítico de contraexemplo →
oráculo). Um pipeline sequencial confundiria as duas variáveis numa única condição —
não daria pra saber se um resultado veio do acesso ao gabarito ou da forma do
feedback. Como condições paralelas, cada uma varia **um único eixo** em relação ao
Crítico original, o que permite atribuir causa, não só observar efeito.

---

## 6. Resultados

### Resultado consolidado (60/60 tarefas, rodada fechada)

| Condição | Resolvidas | Acurácia | Consist. treino | Tokens/tarefa |
|---|---|---|---|---|
| `sampling` | 19/60 | 31,7% | 36,7% | ~25,8 k |
| `critic` (corrigido) | 23/60 | **38,3%** | 41,7% | ~44,3 k |
| `critic_no_oracle` | 17/60 | 28,3% | 33,3% | ~41,6 k |
| `critic_cegis` | 16/60 | 26,7% | 30,0% | ~46,3 k |

**As 5 comparações pré-registradas**, com correção de Bonferroni (α = 0,05 / 5 = 0,01,
porque são 5 testes simultâneos sobre o mesmo conjunto de dados):

| Par | Discordantes | McNemar (p) | Significativo a α=0,01? |
|---|---|---|---|
| `sampling` vs `critic` | 6 (1×5) | 0,2188 | não |
| `sampling` vs `critic_no_oracle` | 10 (6×4) | 0,7539 | não |
| `sampling` vs `critic_cegis` | 7 (5×2) | 0,4531 | não |
| `critic` vs `critic_no_oracle` | 10 (8×2) | 0,1094 | não |
| `critic` vs `critic_cegis` | 9 (8×1) | **0,0391** | não (não sobrevive à correção) |

> **Nenhuma comparação é estatisticamente significativa.** A direção observada
> (`critic` corrigido acima de `sampling`) **inverteu** frente a uma calibração menor
> de 30 tarefas, onde `critic` tinha ficado abaixo — e, curiosamente, o McNemar de
> `sampling` vs `critic` deu **o mesmo p-valor nas duas rodadas (0,2188)**, porque as
> contagens de discordância se inverteram exatamente (5×1 numa, 1×5 na outra) e o
> teste é simétrico a essa troca. É uma demonstração direta de que, nesse tamanho de
> amostra, o sinal observado é ruído — a mesma força de evidência sustentando direções
> opostas.

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

`critic` vs `critic_cegis` chegou a **p = 0,0127** nessa amostra parcial — ainda não
cruza o limiar de Bonferroni (0,01), mas bem mais perto do que com 60 tarefas
(0,0391). Como o próprio projeto já registrou na extensão de 100→270 tarefas da
rodada original: analisar os mesmos dados em mais de um tamanho de amostra infla o
erro tipo I, então **este número interino não substitui a análise final** — ele só
indica que vale continuar até fechar as 270.

---

## 7. Exemplos reais — quando funcionou e quando não

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

---

## 8. Limitações, declaradas

1. **Escala menor que a rodada original** (60–270 em extensão vs 270 fechada) —
   poder estatístico limitado por desenho.
2. **3 das 9 chaves de API usadas têm credencial quebrada** (erro 401 permanente),
   reduzindo a capacidade disponível para a extensão.
3. **`critic` consome ~72% mais tokens por tarefa que `sampling`** — o orçamento é
   medido em chamadas, não em tokens; sob orçamento em tokens, a comparação seria
   menos favorável a ele.
4. Execução única por tarefa — parte da variação é ruído do próprio modelo, mitigado
   pelo pareamento, não eliminado.
5. O oráculo não é autônomo — mede o valor da validação por oposição, não um sistema
   utilizável em produção.

---

## 9. Conclusão e próximo passo

- Um bug real foi encontrado e corrigido — validado com evidência qualitativa, não só
  pela mudança de código.
- Dois críticos novos foram implementados para isolar duas causas distintas de um
  resultado nulo anterior: acesso à informação vs. forma do feedback.
- Nenhuma das 5 comparações pré-registradas é significativa na amostra fechada de 60
  tarefas; a extensão para 270 está em andamento e, até aqui, aponta na mesma direção
  sem cruzar o limiar de significância.
- **Próximo experimento que os resultados justificam:** terminar a extensão para 270
  tarefas (mesma escala da rodada original) e resolver as chaves de API quebradas
  antes de comprometer mais tempo de execução.

> A conclusão não é "o Crítico não funciona" — é "não temos evidência suficiente pra
> dizer que funciona, e agora sabemos exatamente qual experimento rodar pra descobrir".

---

## 10. Perguntas e respostas antecipadas

<details>
<summary><b>Por que comparar contra "amostragem independente" e não outra coisa?</b></summary>

O orçamento controla **chamadas de API**, não programas. Nada obriga quem recebe N
chamadas a gastá-las revisando uma tentativa só — pode gastar gerando N candidatos
independentes. Medir a intervenção contra uma alternativa que gasta o orçamento pior
daria uma vantagem que fala mais do comparativo escolhido do que do método.
</details>

<details>
<summary><b>O que significa "desenho pareado"?</b></summary>

As mesmas tarefas rodam em todas as condições, com o mesmo orçamento. Isso controla o
ruído entre tarefas — algumas são inerentemente mais fáceis que outras — e permite
perguntar não "quantas cada condição acertou", mas "quando as duas condições viram a
mesma tarefa, qual decidiu diferente, e pra que lado". É essa segunda pergunta que o
McNemar responde.
</details>

<details>
<summary><b>Por que os críticos novos são condições paralelas, e não um pipeline (gerador → crítico 1 → crítico de contraexemplo → oráculo)?</b></summary>

Um pipeline sequencial confundiria duas variáveis numa única condição: não daria pra
saber se um resultado veio do acesso ao gabarito ou da forma do feedback. Como
condições paralelas, cada uma varia um único eixo em relação ao Crítico original —
isso é o que permite atribuir causa, não só observar efeito.
</details>

<details>
<summary><b>Como vocês descobriram o bug do oráculo?</b></summary>

Auditando o fluxo de dados do Crítico depois de ler o resultado nulo da rodada de 270
tarefas — não foi pedido de antemão. A função `critic_request` montava a mensagem
enviada ao Crítico usando só `proposal.rule`; `proposal.code` estava disponível no
ponto de chamada, mas nunca era passado adiante.
</details>

<details>
<summary><b>Corrigir isso não abre uma brecha de vazamento nova?</b></summary>

Não. O filtro anti-vazamento (`guards.sanitize`) atua sobre a **saída** do Crítico,
nunca sobre a entrada — e o código do Gerador não é informação secreta, é a própria
saída do Gerador. Dar essa entrada ao Crítico não é vazamento novo nenhum.
</details>

<details>
<summary><b>O que é CEGIS e por que usar esse formato?</b></summary>

CEGIS = *Counterexample-Guided Inductive Synthesis*, técnica citada na própria
especificação do projeto. Em vez de até 150 palavras de prosa livre, o
`critic_cegis` devolve um contraexemplo único e um rótulo de correção de vocabulário
fechado — testando se a forma estruturada do feedback muda o resultado, mantendo o
mesmo acesso à informação do Crítico original.
</details>

<details>
<summary><b>Como garantem que o Crítico não vaza a resposta pro Gerador?</b></summary>

Três camadas: o prompt de sistema proíbe explicitamente escrever
grades/código/coordenadas; o filtro `guards.sanitize` redige automaticamente
qualquer grade ou bloco de código que apareça na resposta, contando cada redação
como um "leak_event"; e há testes automatizados que travam essa separação (inclusive
um teste adversarial, alimentando o crítico sem oráculo com uma resposta
"alucinando" uma grade). Nesta rodada, `leak_events = 0` nas quatro condições.
</details>

<details>
<summary><b>Por que McNemar exato e não qui-quadrado comum?</b></summary>

O desenho é pareado por construção, então o que importa não é a acurácia bruta, é
quantas tarefas cada condição resolveu que a outra não. McNemar é o teste certo pra
essa pergunta. A versão **exata** (binomial) evita a aproximação qui-quadrado, pouco
confiável quando há poucas discordâncias — exatamente nosso caso (6 a 10 por par).
</details>

<details>
<summary><b>Por que correção de Bonferroni? Não é conservadora demais?</b></summary>

É a mais simples e a mais conservadora — intencional: com 5 comparações declaradas
antes de rodar, sobre o mesmo conjunto de dados, o risco de inflar falso-positivo é
real. Mesmo sem correção nenhuma, só 1 das 5 comparações cruzaria α=0,05 na amostra
de 60 tarefas — então a escolha do método não muda a conclusão qualitativa.
</details>

<details>
<summary><b>A direção do efeito inverteu entre a calibração e a rodada de 60 tarefas. Isso não invalida o resultado?</b></summary>

É o oposto — é o próprio achado. Na calibração, `critic` corrigido tinha 23,3% contra
36,7% de `sampling`; na rodada de 60, 38,3% contra 31,7%. O McNemar de `sampling` vs
`critic` deu o mesmo p-valor nas duas (0,2188), porque as contagens de discordância
se inverteram exatamente e o teste é simétrico a essa troca — demonstração direta de
que, nesse tamanho de amostra, o sinal é ruído.
</details>

<details>
<summary><b>O resultado é nulo — isso não é um fracasso do projeto?</b></summary>

Não, e a própria especificação do projeto diz isso: "melhorar o desempenho é
desejável, mas não é condição para um bom projeto". Um resultado nulo bem medido
responde a pergunta orientadora tão bem quanto um resultado positivo — e o intervalo
de confiança diz precisamente quanto uma vantagem do Crítico não pode ser.
</details>

<details>
<summary><b>Por que só 60–270 tarefas em vez de já ter os 270 fechados?</b></summary>

Decisão deliberada de calibração/tempo diante de cota de API limitada — o mesmo
padrão que o próprio projeto já seguiu antes da rodada oficial (uma calibração de 30
tarefas primeiro). A extensão para 270 está em andamento no momento desta
apresentação, retomada a cada folga de cota.
</details>

<details>
<summary><b>Os resultados são reprodutíveis?</b></summary>

Seed fixa (20260814), lista literal de `task_ids` gravada no manifesto de cada
rodada, hash dos prompts de sistema pra auditar integridade, e os `.jsonl` brutos de
cada rodada commitados no repositório — não são regeráveis de forma idêntica (o
modelo não é determinístico), então viraram parte da evidência permanente.
</details>

<details>
<summary><b>O que vocês fariam a seguir?</b></summary>

Terminar a extensão pra 270 tarefas com poder estatístico suficiente pra confirmar ou
descartar a direção observada aqui, e resolver as chaves de API com credencial
quebrada antes de comprometer mais tempo de execução.
</details>

---

<sub>Repositório: `proj-ciencia-inovacao-projeto-1` · branch `feat/critic-oracle-fix` ·
dados brutos em `results/runs/critic-official/` · detalhes completos em
[`docs/results.md`](results.md), [`docs/experimental-decisions.md`](experimental-decisions.md)
e [`docs/exemplo-execucao-criticos-novos.md`](exemplo-execucao-criticos-novos.md).</sub>
