#!/usr/bin/env bash
# Compila artigo.tex usando o TeX Live isolado em ../../.tex-venv/TinyTeX.
# Não usa nem altera nenhuma instalação de LaTeX do sistema.
#
#   bash compilar.sh          # compila
#   bash compilar.sh --limpo  # compila e apaga os intermediários
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEXVENV="$(cd "$AQUI/../.." && pwd)/.tex-venv/TinyTeX"
BIN="$TEXVENV/bin/windows"
[ -d "$BIN" ] || BIN="$TEXVENV/bin/win32"

if [ ! -x "$BIN/pdflatex.exe" ] && [ ! -x "$BIN/pdflatex" ]; then
  echo "ERRO: TeX Live isolado não encontrado em $TEXVENV" >&2
  echo "      Rode primeiro a instalação descrita em LEIAME-artigo.md." >&2
  exit 1
fi

export PATH="$BIN:$PATH"
cd "$AQUI"

echo "== pdflatex (1/4) =="
pdflatex -interaction=nonstopmode -halt-on-error artigo.tex > /dev/null 2>&1 || {
  echo "FALHOU. Últimos erros:"; grep -A 4 "^!" artigo.log | head -40; exit 1; }

echo "== bibtex (2/4) =="
bibtex artigo > /dev/null 2>&1 || { echo "AVISO: bibtex reclamou"; }
grep -E "^(Warning|I couldn't|Repeated)" artigo.blg | head -10 || true

echo "== pdflatex (3/4) =="
pdflatex -interaction=nonstopmode artigo.tex > /dev/null 2>&1 || true

echo "== pdflatex (4/4) =="
pdflatex -interaction=nonstopmode artigo.tex > /dev/null 2>&1 || true

echo
echo "== diagnóstico =="
grep -c "^!" artigo.log | sed 's/^/erros: /' || true
grep -E "Overfull \\\\hbox" artigo.log | wc -l | sed 's/^/overfull hbox: /'
grep -E "Underfull \\\\vbox" artigo.log | wc -l | sed 's/^/underfull vbox: /'
grep -E "LaTeX Warning: (Citation|Reference)" artigo.log | sort -u | head -20 || true
if command -v pdfinfo >/dev/null 2>&1; then pdfinfo artigo.pdf | grep -E "^Pages|^Page size"; fi
ls -la artigo.pdf

if [ "${1:-}" = "--limpo" ]; then
  rm -f artigo.aux artigo.bbl artigo.blg artigo.log artigo.out
  echo "intermediários removidos"
fi
