"""Verificação estática de artigo.tex — não substitui a compilação, mas pega
os erros que uma compilação em outra máquina custaria a achar:
macros usadas sem definição, \\ref sem \\label, \\cite sem entrada no .bib,
comandos e pacotes proibidos pelo AuthorKit 2027.

    python check_artigo.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
TEX = (HERE / "artigo.tex").read_text(encoding="utf-8")
BIB = (HERE / "artigo.bib").read_text(encoding="utf-8")

problemas = []


def erro(msg):
    problemas.append(msg)


# ---------------------------------------------------------------- macros ----
definidas = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", TEX))
definidas |= set(re.findall(r"\\renewcommand\{\\([A-Za-z]+)\}", TEX))

# comandos do LaTeX/AAAI/TikZ que não precisam de definição local
CONHECIDOS = set(
    """documentclass usepackage urlstyle def UrlFont frenchspacing pdfinfo
    setcounter title author affiliations begin end maketitle bibliography
    section subsection paragraph textbf textit emph texttt textsuperscript
    itemize enumerate item cite citep citet ref label caption centering small
    scriptsize footnotesize itemsep noindent quote sim le ge times star pi
    Delta mathbf mathrm frac sqrt sum overset qquad quad hat LaTeX TeX ldots
    tikzpicture tikzset node draw fill foreach usetikzlibrary circle rectangle
    toprule midrule bottomrule multicolumn cmidrule
    figure table equation newcommand renewcommand figurename tablename
    abstractname refname abstract mathbb mathcal text left right
    includegraphics graphicspath itshape upshape bfseries gray black white
    Latex xshift yshift anchor font pos
    """.split()
)

usadas = set(re.findall(r"\\([A-Za-z]+)", TEX))
faltando = sorted(u for u in usadas - definidas - CONHECIDOS if len(u) > 1)
# heurística: só reclama de macros que "parecem" do painel (CamelCase própria)
suspeitas = [u for u in faltando if re.match(r"^[A-Z][a-z]", u) or u.islower() and u in {
    "modelo", "orcamento", "semente", "divisao", "alfaBonf", "numComparacoes",
    "vereditoUm", "vereditoDois", "sigMaisProxima",
}]
for u in suspeitas:
    erro(f"macro possivelmente indefinida: \\{u}")

nao_usadas = sorted(
    d for d in definidas
    if d not in {"figurename", "tablename", "abstractname", "refname"}
    and len(re.findall(r"\\" + d + r"(?![A-Za-z])", TEX)) < 2
)
for d in nao_usadas:
    erro(f"macro definida mas nunca usada no texto: \\{d}")

# --------------------------------------------------------- refs e labels ----
labels = set(re.findall(r"\\label\{([^}]+)\}", TEX))
refs = set(re.findall(r"\\ref\{([^}]+)\}", TEX))
for r in sorted(refs - labels):
    erro(f"\\ref{{{r}}} sem \\label correspondente")
for l in sorted(labels - refs):
    erro(f"\\label{{{l}}} nunca referenciado")

# ------------------------------------------------------------- citações -----
chaves_bib = set(re.findall(r"@\w+\{([^,]+),", BIB))
citadas = set()
for grupo in re.findall(r"\\cite[tp]?\{([^}]+)\}", TEX):
    citadas |= {c.strip() for c in grupo.split(",")}
for c in sorted(citadas - chaves_bib):
    erro(f"\\cite{{{c}}} sem entrada em artigo.bib")
for c in sorted(chaves_bib - citadas):
    erro(f"entrada em artigo.bib nunca citada: {c}  (o AuthorKit pede .bib enxuto)")

# ------------------------------------------- restrições do AuthorKit 2027 ----
PROIBIDOS_PKG = """authblk babel balance cjk epsf epsfig euler float fullpage
    geometry graphics hyperref layout lmodern navigator pdfcomment pgfplots
    psfig pstricks t1enc times titlesec tocbibind ulem indentfirst multicol
    nameref savetrees setspace stfloats tabu wrapfig""".split()
for pkg in PROIBIDOS_PKG:
    if re.search(r"\\usepackage(\[[^\]]*\])?\{[^}]*\b" + pkg + r"\b", TEX):
        erro(f"pacote proibido pelo AuthorKit: {pkg}")

PROIBIDOS_CMD = ["\\addtolength", "\\balance", "\\baselinestretch", "\\clearpage",
                 "\\columnsep", "\\newpage", "\\pagebreak", "\\pagestyle",
                 "\\tiny", "\\vspace{-", "\\vskip{-", "\\linespread",
                 "\\topmargin", "\\textheight", "\\textwidth{", "\\parindent",
                 "\\parskip"]
for cmd in PROIBIDOS_CMD:
    if cmd in TEX:
        erro(f"comando proibido pelo AuthorKit: {cmd}")

# --------------------------------------------------- balanceamento básico ----
for amb in ["document", "abstract", "tikzpicture", "tabular", "figure", "table",
            "itemize", "enumerate", "equation", "quote"]:
    a = len(re.findall(r"\\begin\{" + amb + r"\}", TEX))
    f = len(re.findall(r"\\end\{" + amb + r"\}", TEX))
    if a != f:
        erro(f"ambiente desbalanceado: {amb} ({a} begin, {f} end)")

if TEX.count("{") != TEX.count("}"):
    erro(f"chaves desbalanceadas: {TEX.count('{')} abre, {TEX.count('}')} fecha")

# ------------------------------------------------------ marcas de veredito ---
CORPO = TEX.split(r"\begin{document}", 1)[-1]

# --------------------------------------- espaço comido por macro sem chaves ---
# "\Bp\n(Equação" vira "0,8877(Equação": o TeX engole o espaço depois de um
# nome de comando. Só é problema quando a linha seguinte NÃO começa por espaço.
for m in re.finditer(r"\\([A-Za-z]+)[ \t]*\n(?=[^\s%])", CORPO):
    nome = m.group(1)
    if nome in definidas:
        linha = CORPO[: m.start()].count("\n") + 1
        erro(f"\\{nome} no fim de linha engole o espaço seguinte "
             f"(corpo, linha ~{linha}) — use \\{nome}{{}}")

# --------------------------- veredito iniciando frase em letra minúscula ------
for macro in ("vereditoUm", "vereditoDois"):
    corpo_macro = re.search(r"\\newcommand\{\\" + macro + r"\}\{(.)", TEX)
    if corpo_macro and corpo_macro.group(1).islower():
        for m in re.finditer(r"([.!?])\s+\\" + macro + r"\b", CORPO):
            linha = CORPO[: m.start()].count("\n") + 1
            erro(f"\\{macro} (começa em minúscula) inicia frase após "
                 f"'{m.group(1)}' no corpo, linha ~{linha}")
n_veredito = CORPO.count("% >>> VEREDITO")
if n_veredito != 6:
    erro(f"esperava 6 marcas '% >>> VEREDITO' no corpo, encontrei {n_veredito}")

# ---------------------------------------------------------------- saída -----
if problemas:
    print(f"{len(problemas)} ponto(s) a revisar:\n")
    for p in problemas:
        print("  -", p)
    sys.exit(1)
print("OK — artigo.tex e artigo.bib consistentes.")
print(f"   {len(definidas)} macros no painel, {len(labels)} labels, "
      f"{len(citadas)} referências citadas.")
