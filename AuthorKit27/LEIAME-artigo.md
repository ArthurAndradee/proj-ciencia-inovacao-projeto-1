# `artigo.tex` — compilação e atualização

Artigo em português no template AAAI 2027 (`aaai2027.sty`, `aaai2027.bst`).
Fontes: `docs/*.md` e `README.md` do repositório.

**Estado atual:** 5 páginas, 0 erros, 0 `Overfull \hbox`, 0 avisos do LaTeX.
**Limite de extensão: 6 páginas.** Compile antes de acrescentar qualquer
parágrafo, figura ou tabela.

## Compilar

```bash
bash compilar.sh          # pdflatex → bibtex → pdflatex ×2 + diagnóstico
bash compilar.sh --limpo  # idem, apagando os intermediários
```

O script usa um TeX Live isolado em `../../.tex-venv/TinyTeX`, fora do
repositório — não depende de nem altera nenhuma instalação de LaTeX do sistema.
Para reinstalá-lo:

```bash
mkdir -p ../../.tex-venv && cd ../../.tex-venv
curl -sLO https://github.com/rstudio/tinytex-releases/releases/download/v2026.09/TinyTeX-v2026.09.zip
unzip -q TinyTeX-v2026.09.zip     # cria ./TinyTeX
```

No Overleaf, subir **apenas** `artigo.tex`, `artigo.bib`, `aaai2027.sty` e
`aaai2027.bst`; compiler pdfLaTeX. Não há figura externa — as cinco são TikZ
dentro do `.tex`.

## Validar sem compilar

```bash
python check_artigo.py
```

Verifica macros do painel definidas e usadas, `\ref` com `\label`, `\cite` com
entrada no `.bib` (e o inverso, que o AuthorKit exige), pacotes e comandos
proibidos, ambientes balanceados, as 4 marcas de veredito, macros no fim de linha
que engolem o espaço seguinte e vereditos em minúscula iniciando frase.

## Estrutura

```
Resumo
1  Introdução
2  Trabalho Relacionado
3  Metodologia        3.1 Formulação · 3.2 Condições · 3.3 Salvaguardas e Análise
4  Resultados         4.1 Comparação em Escala
                      4.2 A Origem das Vitórias
                      4.3 Reprodutibilidade da Ordenação
5  Discussão e Limitações
6  Conclusão
```

**Floats (6):** Fig. 1 arquitetura · Fig. 2 matriz de condições · Tab. 1
resultados agregados · Fig. 3 intervalos de confiança · Fig. 4 decomposição das
vitórias · Fig. 5 reprodutibilidade da ordenação.

O achado central é o **desconto da primeira geração** (4.2): metade das vitórias
de qualquer condição vem de uma chamada idêntica entre elas, o experimento
discrimina em ~1/5 da amostra, e a ordenação inverte ao descontar essa parcela.

## Atualizar quando os resultados mudarem

Nenhum número está digitado solto no corpo. Tudo vem do **`PAINEL DE
RESULTADOS`** no topo de `artigo.tex`, lido também pelas figuras TikZ — mudar o
painel atualiza texto e gráficos juntos.

1. **Números.** Macros terminadas em `N` são a versão numérica (ponto decimal)
   usada pelas figuras; a irmã, sem `N`, é a de exibição (vírgula). Vêm em pares
   na mesma linha — troque as duas. Valores com sinal usam
   `\mbox{$-$14{,}8}`, que compila em texto e em modo matemático; mantenha.
2. **Vereditos.** `\vereditoUm`, `\vereditoDois` e `\vereditoTres` carregam as
   três afirmações interpretativas do artigo.
3. **Parágrafos de leitura.** Apenas os quatro marcados com `% >>> VEREDITO`
   (resumo, 4.1, 4.2, conclusão) afirmam o sinal do resultado. O título é neutro
   e não muda.
4. **Números que não vêm do repositório.** Dois blocos foram calculados fora do
   código do projeto:
   - **Intervalos de confiança** (Fig. 3): `metrics.py` não implementa Wilson.
     Calculados pela Equação 2 e validados contra a medição sob o protocolo
     anterior, cujo IC publicado em `docs/results.md` é reproduzido exatamente.
   - **Reprodutibilidade da ordenação** (Fig. 5): `python reamostragem.py`,
     versionado aqui. Subamostragem sem reposição das próprias 270 tarefas,
     20.000 repetições por tamanho, preservando o pareamento.

## O que ficou de fora, deliberadamente

O artigo apresenta o recorte necessário para sustentar a contribuição, não tudo
que o projeto produziu. Não entraram: as notas de execução (chamadas, chaves,
cota de API), a tabela de seleção de modelo, a família de comparações em forma de
tabela, as comparações restritas em forma de tabela, a análise qualitativa de
casos individuais, os estudos-piloto de 30 e 60 tarefas e os agregados completos
da medição sob o protocolo anterior. Todos permanecem em `docs/results.md` e no
histórico do repositório.

## Desvios do AuthorKit, declarados

1. **Figuras em TikZ inline.** O kit não proíbe `tikz` (proíbe `pgfplots`), mas
   recomenda pré-gerar figuras e importá-las com `\includegraphics`. TikZ é o que
   permite que as figuras leiam o painel de resultados.
2. **`\renewenvironment{abstract}`.** O `aaai2027.sty` escreve "Abstract"
   literalmente e ignora `\abstractname`. O bloco no preâmbulo é cópia exata da
   definição do estilo trocando só a palavra — nenhuma métrica muda.
   **Apague-o** para submeter à AAAI.
3. **`babel` é proibido**, então não há hifenização portuguesa e os nomes dos
   flutuantes são redefinidos à mão.
4. **`\setlength{\tabcolsep}{4pt}`** local à Tabela 1. Não é comando de layout de
   página nem está na lista de proibidos.

## Pendências

- **Autoria.** Está como `Anonymous Submission` (opção `submission` do estilo).
  Para a versão identificada, trocar por `\author{...}` / `\affiliations{...}` e
  remover a opção `submission`.
- **Uso de IA.** O registro proporcional pendente no `README.md` (§6 da
  especificação) não foi incorporado ao artigo — é autoavaliação da equipe.
