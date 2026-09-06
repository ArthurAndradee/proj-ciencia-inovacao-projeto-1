# `artigo.tex` — compilação e atualização

Artigo em português no template AAAI 2027 (`aaai2027.sty`, `aaai2027.bst`).
Fontes: `docs/*.md` e `README.md` do repositório.

**Estado atual:** 5 páginas, 1 figura, 3 tabelas, 18 referências. Compila limpo —
0 erros, 0 `Overfull \hbox`, 0 avisos do LaTeX.

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

Para o Overleaf, subir apenas quatro arquivos: `artigo.tex`, `artigo.bib`,
`aaai2027.sty` e `aaai2027.bst`. Compilador pdfLaTeX, documento principal
`artigo.tex`. Não há figuras externas — a única figura é TikZ inline.

## Validar sem compilar

```bash
python check_artigo.py
```

Verifica macros do painel definidas e usadas, `\ref` com `\label`, `\cite` com
entrada no `.bib` (e o inverso, que o AuthorKit exige), pacotes e comandos
proibidos, ambientes balanceados, as 3 marcas de veredito, macros no fim de linha
que engolem o espaço seguinte, e vereditos em minúscula abrindo frase ou
parágrafo. Rode depois de qualquer edição.

## Estrutura

```
Resumo
1  Introdução
2  Trabalho Relacionado
3  Metodologia
   3.1 Formulação e Condições        (Tabela 1)
   3.2 Salvaguardas Contra Contaminação pelo Oráculo
   3.3 Procedimento e Análise
4  Resultados                        (Tabelas 2 e 3)
   4.1 A Origem das Vitórias         (Figura 1)
5  Discussão
6  Conclusão
Reprodutibilidade · Referências
```

O artigo sustenta duas afirmações, nesta ordem de importância:

1. Nenhuma das 5 comparações pré-registradas é significativa — nem sob
   Bonferroni, nem a α = 0,05 sem correção.
2. Cerca de metade das vitórias de qualquer condição é decidida na primeira
   geração, idêntica entre elas; descontada essa parcela, a medição discrimina em
   ~1/5 da amostra e a ordenação entre condições inverte.

## Atualizar quando os resultados mudarem

Nenhum número está digitado solto no corpo. Tudo vem do bloco
**`PAINEL DE RESULTADOS`** no topo de `artigo.tex`, e a figura lê as mesmas
macros — mudar o painel atualiza texto, tabelas e gráfico juntos.

1. **Números.** Troque os valores no painel. Macros terminadas em `N` são a
   versão numérica com ponto decimal, consumida pela figura; a irmã sem `N` é a
   de exibição. Vêm em pares na mesma linha — troque as duas. Valores com sinal
   usam a forma `\mbox{$-$14{,}8}`, que compila em modo texto e matemático;
   mantenha o formato.
2. **Vereditos.** `\vereditoUm` e `\vereditoDois`, logo abaixo do painel,
   carregam as duas afirmações reusadas no resumo, nos resultados e na conclusão.
   Ambas começam em minúscula, para uso no meio de frase — o validador avisa se
   alguma passar a abrir frase ou parágrafo.
3. **Parágrafos de leitura.** Apenas os três marcados com `% >>> VEREDITO`
   (resumo, resultado principal, conclusão) afirmam o sinal do resultado. O
   título é neutro e não precisa mudar.
4. **Números calculados fora do repositório.** Dois blocos precisam ser refeitos
   se os dados mudarem:
   - Os **intervalos de confiança** (Tabela 3): `metrics.py` não implementa
     Wilson. Calculados pela fórmula padrão e validados contra a medição de duas
     condições sobre as mesmas tarefas, cujo IC publicado em `docs/results.md` é
     reproduzido exatamente.
   - A **estabilidade sob subamostragem** (dois números na Discussão): rode
     `python reamostragem.py`, que lê `results/runs/critic-official/`.

## Desvios do AuthorKit, declarados

1. **Figura em TikZ inline.** O kit não proíbe `tikz` (proíbe `pgfplots`), mas
   recomenda pré-gerar figuras e importá-las com `\includegraphics`. A escolha
   por TikZ é o que permite que a figura leia o painel de resultados.
2. **`\renewenvironment{abstract}`.** O `aaai2027.sty` escreve "Abstract"
   literalmente e ignora `\abstractname`. O bloco no preâmbulo é cópia exata da
   definição do estilo trocando só a palavra por "Resumo" — nenhuma métrica de
   fonte, espaçamento ou margem muda. **Apague-o** para submeter à AAAI.
3. **`babel` é proibido**, então não há hifenização portuguesa e os nomes dos
   flutuantes são redefinidos à mão.
4. **`\setlength{\tabcolsep}{4pt}`** local a cada tabela. Não é comando de layout
   de página nem está na lista de proibidos; é o que mantém as tabelas dentro da
   coluna.

## Pendências

- **Autoria.** Está como `Anonymous Submission` (opção `submission` do estilo).
  Para a versão identificada, trocar por `\author{...}` / `\affiliations{...}` e
  remover a opção `submission`.
- **Uso de IA.** O registro proporcional pendente no `README.md` (§6 da
  especificação) não foi incorporado ao artigo — é autoavaliação da equipe.
