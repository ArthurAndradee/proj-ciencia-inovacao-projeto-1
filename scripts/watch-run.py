#!/usr/bin/env python3
"""Acompanha uma rodada de `arc-exp run` em andamento e sinaliza problemas.

    uv run python scripts/watch-run.py                          # uma leitura
    uv run python scripts/watch-run.py --interval 60            # a cada 60 s
    uv run python scripts/watch-run.py --interval 60 --log run.log

Lê o que já está gravado em disco (`<condição>.jsonl`) — a rodada escreve cada
tarefa assim que ela termina, então o progresso é observável sem tocar no
processo. Não interfere na execução: só lê arquivos e consulta o `ps`.

Código de saída: 0 saudável · 1 com alertas · 2 processo não está mais rodando.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR: Path = REPO_ROOT / "results" / "runs" / "critic-official"
CONDITIONS: tuple[str, ...] = ("sampling", "critic", "critic_no_oracle", "critic_cegis")

# Uma tarefa pode demorar: o crítico gasta até 7 chamadas, cada uma sujeita ao
# throttle e à latência do modelo — e, quando todas as chaves estão de molho, o
# pool espera até 5 min antes de tentar de novo. Só acima disso o silêncio vira
# sintoma.
STALL_MINUTES: float = 12.0

# O que o CLI imprime quando algo dá errado (cli.command_run e key_usage_table).
LOG_ALERTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chave rejeitada e descartada do pool", re.compile(r"REJECTED by the API")),
    ("o pool ficou sem chave para servir", re.compile(r"No API key left to serve")),
    ("API rejeitou a requisição (erro permanente)", re.compile(r"API rejected the request", re.I)),
    ("interrompido por Ctrl+C", re.compile(r"Interrupted\. Finished tasks are saved")),
    ("traceback do Python", re.compile(r"^Traceback \(most recent call", re.M)),
)


def find_run_process() -> tuple[int | None, float]:
    """PID do `arc-exp run` em andamento e há quantos segundos ele roda."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "arc-exp run"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None, 0.0
    pids = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
    if not pids:
        return None, 0.0
    pid = pids[0]
    try:
        # `etimes` (segundos) não existe no ps do macOS; `etime` existe em ambos
        # e vem como [[dd-]hh:]mm:ss. Pedir o que não existe fazia o ps falhar e
        # o watcher relatar "rodando há 0 min" para qualquer processo.
        out2 = subprocess.run(
            ["ps", "-p", str(pid), "-o", "etime="], capture_output=True, text=True, timeout=10
        )
        return pid, _parse_etime(out2.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return pid, 0.0


def _parse_etime(text: str) -> float:
    """[[dd-]hh:]mm:ss -> segundos."""
    if not text:
        return 0.0
    days = 0
    if "-" in text:
        head, text = text.split("-", 1)
        days = int(head)
    parts = [float(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def read_records(path: Path) -> list[dict[str, Any]]:
    """Registros já gravados, tolerando a última linha ainda pela metade."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def expected_tasks(run_dir: Path, fallback: int) -> int:
    """Tarefas por condição: o manifesto manda, mas nunca abaixo do que já há em disco.

    O manifesto de uma rodada anterior sobrevive no diretório até o novo
    `run_experiment` reescrevê-lo, e um manifesto de 60 faria o watcher
    reportar 270/60 antes de a rodada nova começar.
    """
    counts: list[int] = [fallback]
    manifest = run_dir / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            counts.append(len(data.get("task_ids") or []))
        except (OSError, json.JSONDecodeError):
            pass
    for name in CONDITIONS:
        counts.append(len(read_records(run_dir / f"{name}.jsonl")))
    return max(counts)


def error_kinds(rows: list[dict[str, Any]]) -> dict[str, int]:
    kinds: dict[str, int] = {}
    for row in rows:
        if row.get("error"):
            key = str(row["error"])[:70]
            kinds[key] = kinds.get(key, 0) + 1
    return kinds


def report(run_dir: Path, log_path: Path | None, total_tasks: int) -> tuple[str, list[str], bool]:
    lines: list[str] = []
    problems: list[str] = []
    pid, elapsed_s = find_run_process()
    running = pid is not None

    stamp = datetime.now().strftime("%H:%M:%S")
    where = f"pid {pid}, rodando há {elapsed_s / 60:.0f} min" if running else "nenhum processo"
    lines.append(f"=== {stamp} · {run_dir.name} · {where} ===")

    # Escopo = o que esta rodada ainda deve. Uma condição já completa (o
    # `sampling` reaproveitado, por exemplo) aparece como referência, mas fora
    # da contagem de progresso e da ETA — senão a barra nasce em 25% feita.
    done = 0
    pending_total = 0
    newest_mtime = 0.0
    for name in CONDITIONS:
        path = run_dir / f"{name}.jsonl"
        rows = read_records(path)
        if path.exists():
            newest_mtime = max(newest_mtime, path.stat().st_mtime)
        complete = len(rows) >= total_tasks
        solved = sum(1 for r in rows if r.get("solved"))
        leaks = sum(int(r.get("leak_events", 0)) for r in rows)
        trunc = sum(int(r.get("truncated_answers", 0)) for r in rows)
        errors = error_kinds(rows)
        n_err = sum(errors.values())
        acc = f"{100.0 * solved / len(rows):.1f}%" if rows else "  -- "
        filled = min(20, int(20 * len(rows) / total_tasks)) if total_tasks else 0
        bar = "#" * filled + "." * (20 - filled)
        flag = " (completa)" if complete else ""
        lines.append(
            f"  {name:<17} [{bar}] {len(rows):>3}/{total_tasks}  "
            f"resolv. {solved:>3} ({acc:>6})  erros {n_err:>2}  vazam. {leaks:>2}  trunc. {trunc:>3}{flag}"
        )
        if not complete:
            done += len(rows)
            pending_total += total_tasks
        for kind, count in sorted(errors.items(), key=lambda kv: -kv[1])[:2]:
            problems.append(f"{name}: {count} tarefa(s) com erro de API — {kind}")

    if pending_total:
        pct = 100.0 * done / pending_total
        lines.append(f"  {'PENDENTE':<17} {' ' * 22}{done:>3}/{pending_total}  ({pct:.1f}%)")
    else:
        lines.append("  todas as condições estão completas")

    # Ritmo e ETA a partir do tempo de vida do processo: só vale enquanto ele vive.
    if running and elapsed_s > 60 and done:
        # As execuções já em disco antes deste processo começar não contam para
        # o ritmo dele; sem saber quantas eram, a taxa é um piso, e a ETA um teto.
        rate = done / (elapsed_s / 60.0)
        left = pending_total - done
        eta = left / rate if rate else float("inf")
        lines.append(f"  ritmo ≥{rate:.1f} exec./min  ·  faltam {left}  ·  ETA ≲{eta:.0f} min")

    if running and newest_mtime:
        idle = (time.time() - newest_mtime) / 60.0
        lines.append(f"  último resultado gravado há {idle:.1f} min")
        # A idade do arquivo mede a rodada ANTERIOR enquanto esta não gravou
        # nada. Só há estagnação se o processo já viveu mais que o limite.
        if idle > STALL_MINUTES and elapsed_s / 60.0 > STALL_MINUTES:
            problems.append(
                f"nada gravado há {idle:.0f} min (limite {STALL_MINUTES:.0f}) — "
                "possível travamento, 429 em cadeia ou latência alta"
            )

    if log_path is not None and log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in LOG_ALERTS:
            hits = len(pattern.findall(text))
            if hits:
                problems.append(f"log: {label} ({hits}x)")
        tail = [l for l in text.splitlines() if l.strip()][-3:]
        if tail:
            lines.append("  log:")
            lines.extend(f"    {l[:140]}" for l in tail)

    if not running and done:
        problems.append(
            "o processo não está mais rodando — confira se terminou ou parou por cota "
            "(código de saída 2). Repetir o mesmo comando retoma de onde parou."
        )

    return "\n".join(lines), problems, running


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--log", type=Path, default=None, help="log do comando, se houver")
    parser.add_argument("--interval", type=int, default=0, metavar="S",
                        help="repetir a cada S segundos (0 = uma leitura só)")
    parser.add_argument("--tasks", type=int, default=270, help="tarefas esperadas por condição")
    args = parser.parse_args()

    total = expected_tasks(args.run_dir, args.tasks)
    while True:
        text, problems, running = report(args.run_dir, args.log, total)
        print(text, flush=True)
        if problems:
            print("\n!! ALERTAS", flush=True)
            for problem in problems:
                print(f"  - {problem}", flush=True)
        else:
            print("\nsem alertas", flush=True)
        if args.interval <= 0:
            return 2 if not running else (1 if problems else 0)
        if not running:
            return 2
        print(flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
