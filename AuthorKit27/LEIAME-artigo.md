# `artigo.tex` — compilação e atualização

Artigo em português no template AAAI 2027 (`aaai2027.sty`, `aaai2027.bst`).
Fontes: `docs/*.md` e `README.md` do repositório.

**Estado atual:** compila limpo — 0 erros, 0 `Overfull \hbox`, 0 avisos do LaTeX,
10 páginas.

## Compilar

```bash
bash compilar.sh          # pdflatex → bibtex → pdflatex ×2 + diagnóstico
bash compilar.sh --limpo  # idem, apagando os intermediários
```

O script usa um TeX Live isolado em `../../.tex-venv/TinyTeX` (TeX Live 2026 via
TinyTeX), fora do repositório — não depende de nem altera nenhuma instalação de
LaTeX do sistema. Para reinstalá-lo do zero:

```bash
mkdir -p ../../.tex-venv && cd ../../.tex-venv
curl -sLO https://github.com/rstudio/tinytex-releases/releases/download/v2026.09/TinyTeX-v2026.09.zip
unzip -q TinyTeX-v2026.09.zip     # cria ./TinyTeX
```

No Overleaf, subir `artigo.tex`, `artigo.bib`, `aaai2027.sty` e `aaai2027.bst`.

## Validar sem compilar

```bash
python check_artigo.py
```

Verifica: macros do painel definidas e usadas, `\ref` com `\label`, `\cite` com
entrada no `.bib` (e o inverso, que o AuthorKit exige), pacotes e comandos
proibidos, ambientes balanceados, as 5 marcas de veredito, macros no fim de linha
que engolem o espaço seguinte, e vereditos em minúscula iniciando frase. Rode
depois de qualquer edição.

## Estrutura (IMRaD)

```
Resumo
1  Introdução
2  Trabalho Relacionado
3  Metodologia
   3.1 Formulação do Problema        3.5 Parâmetros de Configuração
   3.2 Arquitetura do Solucionador   3.6 Seleção do Modelo
   3.3 Condições Experimentais       3.7 Protocolo de Análise Estatística
   3.4 Salvaguardas                  3.8 Procedimento Experimental
4  Resultados
   4.1 Comparação Principal sob o Protocolo P1   (Experimento 1: 270 tarefas, 2 condições)
   4.2 Decomposição Fatorial em Escala           (Experimento 2: 270 tarefas, 4 condições)
   4.3 A Origem das Vitórias                     (desconto da primeira geração)
   4.4 Estabilidade das Estimativas              (n = 30, 60, 270)
   4.5 Análise Qualitativa
5  Discussão
   5.1 Interpretação  5.2 Implicações Práticas  5.3 Limitações e Ameaças
6  Conclusão
Reprodutibilidade · Referências
```

Toda a metodologia está na Seção 3, incluindo a diferença entre os protocolos
**P1** (Experimento 1, Crítico sem acesso ao código candidato) e **P2**
(Experimento 2 e pilotos, com o código) — declarada como fato metodológico em
3.8 e como limitação em 5.3, não como narrativa de descoberta. O confundimento
temporal (`sampling` coletado em 21/08, condições de crítico em 02–03/09) também
é declarado nos dois lugares.

O achado central do artigo é o **desconto da primeira geração** (4.3): metade das
vitórias de qualquer condição vem de uma chamada idêntica entre elas, o
experimento discrimina em ~1/5 da amostra, e a ordenação entre condições inverte
quando se desconta essa parcela. Ele replica nos dois experimentos, sob os dois
protocolos.

## Atualizar quando os resultados mudarem

Nenhum número está digitado solto no corpo do texto. Tudo vem do bloco
**`PAINEL DE RESULTADOS`** no topo de `artigo.tex`, e as 5 figuras TikZ leem as
mesmas macros — mudar o painel atualiza texto, tabelas e gráficos juntos.

1. **Números.** Troque os valores no painel. Macros terminadas em `N` são a
   versão numérica com ponto decimal, consumida pelas figuras; a macro irmã, sem
   `N`, é a de exibição. Elas vêm em pares na mesma linha — troque as duas.
   Valores com sinal usam a forma `\mbox{$-$14{,}8}`, que compila tanto em modo
   texto quanto matemático; mantenha esse formato.
2. **Vereditos.** As macros `\vereditoUm`, `\vereditoDois` e `\sigMaisProxima`,
   logo abaixo do painel, carregam as afirmações interpretativas curtas reusadas
   no resumo, na introdução e na conclusão.
3. **Parágrafos de leitura.** Apenas os seis marcados com `% >>> VEREDITO`
   (resumo, fim da introdução, 4.1, 4.2, 4.3, conclusão) afirmam o sinal do
   resultado. Os intervalos de confiança da Tabela 7 não vêm de `metrics.py` —
   o repositório não implementa Wilson. Foram calculados pela Equação 3 do
   artigo e validados contra o Experimento 1, cujo IC publicado em
   `docs/results.md` é reproduzido exatamente.
4. **Título.** O título em uso **afirma o achado**, então precisa mudar se o
   sinal inverter. Quatro alternativas estão comentadas logo acima do `\title`,
   sendo as duas últimas neutras (sobrevivem a uma inversão).

## Desvios do AuthorKit, declarados

1. **Figuras em TikZ inline.** O kit não proíbe `tikz` (proíbe `pgfplots`), mas
   recomenda pré-gerar figuras fora do LaTeX e importá-las com
   `\includegraphics`. A escolha por TikZ é o que permite que as figuras leiam o
   painel de resultados. Para conformidade estrita, compilar cada `tikzpicture`
   como `standalone` e trocar por `\includegraphics`.
2. **`\renewenvironment{abstract}`.** O `aaai2027.sty` escreve "Abstract"
   literalmente e ignora `\abstractname`. O bloco no preâmbulo é cópia exata da
   definição do estilo trocando só a palavra por "Resumo" — nenhuma métrica de
   fonte, espaçamento ou margem muda. **Apague-o** para submeter à AAAI.
3. **`babel` é proibido**, então não há hifenização portuguesa e os nomes dos
   flutuantes são redefinidos à mão. Se a restrição não se aplicar,
   `\usepackage[brazil]{babel}` melhora a tipografia.
4. **`\setlength{\tabcolsep}{4pt}`** em cinco tabelas, local a cada uma. Não é
   comando de layout de página e não está na lista de proibidos; é o que mantém
   as tabelas dentro da coluna.

## Pendências

- **Autoria.** Está como `Anonymous Submission` (opção `submission` do estilo).
  Para a versão identificada, trocar por `\author{...}` / `\affiliations{...}` e
  remover a opção `submission`.
- **Extensão.** 10 páginas. Acima do limite típico de uma submissão AAAI, mas
  provavelmente adequado a uma nota técnica de disciplina. Se precisar cortar, a
  ordem sugerida é: a Seção 4.5 (Análise Qualitativa), a Tabela 1 (cujo conteúdo
  o texto já descreve) e a Tabela 3 (a família de comparações, também descrita
  no texto).
- **`SeedCache` não integrado.** O artigo aponta o *commit* `19e492c` (branch
  `feat/project-scaffolding`) como a correção escrita e não aplicada para o
  confundimento dominante. Se ele for integrado e os experimentos refeitos, a
  Seção 4.3 muda de "limitação com correção conhecida" para resultado.
- **Uso de IA.** O registro proporcional pendente no `README.md` (§6 da
  especificação) não foi incorporado ao artigo — é autoavaliação da equipe.
