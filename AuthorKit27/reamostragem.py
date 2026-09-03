"""Análise de estabilidade por subamostragem das próprias 270 tarefas.

Substitui a figura que usava os pilotos históricos de 30 e 60 tarefas (um deles
descartado e refeito). Pergunta: se o experimento tivesse parado em n tarefas,
com que frequência a direção e a ordenação observadas em 270 se manteriam?

Amostragem SEM reposição do conjunto fechado de 270, preservando o pareamento
(as quatro condições são avaliadas no mesmo subconjunto de tarefas).
"""
import json
import random
from pathlib import Path
from statistics import median

RUN = Path(__file__).resolve().parent.parent / "results" / "runs" / "critic-official"
COND = ["sampling", "critic", "critic_no_oracle", "critic_cegis"]
B = 20000
SEED = 20260814
TAMANHOS = [30, 60, 90, 135, 180, 270]


def carrega(nome):
    d = {}
    for linha in (RUN / f"{nome}.jsonl").read_text(encoding="utf-8").splitlines():
        if linha.strip():
            r = json.loads(linha)
            d[r["task_id"]] = bool(r["solved"])
    return d


dados = {c: carrega(c) for c in COND}
tarefas = sorted(set.intersection(*(set(d) for d in dados.values())))
print(f"tarefas pareadas nas quatro condições: {len(tarefas)}")

resolvidas = {c: [dados[c][t] for t in tarefas] for c in COND}
N = len(tarefas)
acc_total = {c: sum(resolvidas[c]) / N for c in COND}
ordem_total = sorted(COND, key=lambda c: -acc_total[c])
print("acurácia em n=270:", {c: round(acc_total[c] * 100, 1) for c in COND})
print("ordenação completa:", ordem_total)
print()

rng = random.Random(SEED)
idx = list(range(N))

print(f"{'n':>5} {'P(critic>samp)':>15} {'P(ordem igual)':>15} "
      f"{'dif p5':>8} {'dif p50':>8} {'dif p95':>8}")
linhas = []
for n in TAMANHOS:
    acertos_dir = 0
    acertos_ordem = 0
    difs = []
    for _ in range(B):
        amostra = rng.sample(idx, n) if n < N else idx
        accs = {c: sum(resolvidas[c][i] for i in amostra) / n for c in COND}
        difs.append((accs["critic"] - accs["sampling"]) * 100)
        if accs["critic"] > accs["sampling"]:
            acertos_dir += 1
        if sorted(COND, key=lambda c: -accs[c]) == ordem_total:
            acertos_ordem += 1
        if n == N:
            break
    reps = B if n < N else 1
    difs.sort()
    p5 = difs[int(0.05 * len(difs))]
    p95 = difs[min(int(0.95 * len(difs)), len(difs) - 1)]
    p50 = median(difs)
    linhas.append((n, acertos_dir / reps, acertos_ordem / reps, p5, p50, p95))
    print(f"{n:>5} {acertos_dir / reps * 100:>14.1f}% {acertos_ordem / reps * 100:>14.1f}% "
          f"{p5:>8.1f} {p50:>8.1f} {p95:>8.1f}")

print()
print("=== macros para o painel do artigo ===")
for n, pdir, pord, p5, p50, p95 in linhas:
    if n in (30, 60, 270):
        print(f"n={n}: P(direção)={pdir * 100:.0f}%  P(ordem)={pord * 100:.0f}%  "
              f"banda 5-95 = [{p5:+.1f}, {p95:+.1f}] pp")

print()
print("=== onde caíram os pilotos históricos? ===")
for nome, n, crit, samp in [("piloto 30", 30, 23.3, 36.7), ("piloto 60", 60, 38.3, 31.7)]:
    alvo = crit - samp
    linha = next(l for l in linhas if l[0] == n)
    dentro = linha[3] <= alvo <= linha[5]
    print(f"  {nome}: dif observada {alvo:+.1f} pp — banda 5-95 "
          f"[{linha[3]:+.1f}, {linha[5]:+.1f}] -> {'DENTRO' if dentro else 'FORA'}")
