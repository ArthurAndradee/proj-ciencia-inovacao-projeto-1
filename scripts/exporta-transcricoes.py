"""Exporta os transcripts do Claude Code para markdown legível."""
import json, sys, glob, re
from datetime import datetime
from pathlib import Path

ORIGEM = Path.home()/".claude/projects/-Users-tobiascadonamarion-Documents-UFRGS-proj-ciencia-inovacao-projeto-1"
DESTINO = Path("prompts")
LIMITE_SAIDA = 900          # chars de output de ferramenta antes de truncar
LIMITE_TEXTO = 100_000      # salvaguarda por mensagem

def limpa(t: str) -> str:
    """Remove blocos de sistema que são ruído de harness, não conversa."""
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.S)
    t = re.sub(r"<local-command-[^>]*>.*?</local-command-[^>]*>", "", t, flags=re.S)
    return t.strip()

def corta(t: str, n: int) -> str:
    t = t.rstrip()
    if len(t) <= n:
        return t
    return t[:n].rstrip() + f"\n… [+{len(t)-n} caracteres omitidos]"

def so_resultado(content) -> bool:
    """True quando a mensagem 'do usuário' é apenas retorno de ferramenta.

    O formato do transcript entrega tool_result como mensagem de usuário. Tratá-la
    como fala da pessoa encheria a transcrição de turnos que ninguém escreveu.
    """
    if isinstance(content, str):
        return False
    blocos = [b for b in (content or []) if isinstance(b, dict)]
    return bool(blocos) and all(b.get("type") == "tool_result" for b in blocos)


def texto_de(content) -> tuple[str, list[str]]:
    """Devolve (texto, lista de chamadas de ferramenta descritas)."""
    if isinstance(content, str):
        return limpa(content), []
    partes, ferramentas = [], []
    for bloco in content or []:
        if not isinstance(bloco, dict):
            continue
        t = bloco.get("type")
        if t == "text":
            partes.append(limpa(bloco.get("text", "")))
        elif t == "thinking":
            pass  # raciocínio interno fica de fora
        elif t == "tool_use":
            nome = bloco.get("name", "?")
            ent = bloco.get("input", {}) or {}
            desc = ent.get("description") or ent.get("command") or ent.get("file_path") or ent.get("prompt") or ""
            ferramentas.append(f"{nome}: {corta(str(desc), 160)}" if desc else nome)
        elif t == "tool_result":
            pass  # a saída fica de fora: o que importa é a decisão, não o maquinário
    return "\n\n".join(p for p in partes if p), ferramentas

def exporta(caminho: Path) -> tuple[Path, dict]:
    registros = []
    for l in caminho.read_text(errors="replace").splitlines():
        if not l.strip():
            continue
        try:
            registros.append(json.loads(l))
        except json.JSONDecodeError:
            continue

    titulo = next((r["aiTitle"] for r in registros if r.get("type")=="ai-title"), None)
    datas = [r["timestamp"] for r in registros if r.get("timestamp")]
    inicio = min(datas)[:10] if datas else "sem-data"
    ramo = next((r.get("gitBranch") for r in registros if r.get("gitBranch")), "—")

    linhas, n_user, n_assist, n_tools = [], 0, 0, 0
    # Um turno do Claude chega partido em vários registros (texto, chamada, texto...).
    # Agrupamos os consecutivos, preservando a ordem: a sequência entre o que foi dito
    # e o que foi executado é o que torna a transcrição legível.
    buffer, buffer_hora = [], None

    def descarrega():
        nonlocal buffer, buffer_hora, n_assist
        if not buffer:
            return
        n_assist += 1
        saida, ferramentas = [], []

        def fecha_ferramentas():
            if ferramentas:
                lista = "\n".join(f"- `{f}`" for f in ferramentas)
                saida.append(f"<sub>ferramentas</sub>\n{lista}")
                ferramentas.clear()

        for tipo_item, valor in buffer:
            if tipo_item == "txt":
                fecha_ferramentas()
                saida.append(valor)
            else:
                ferramentas.append(valor)
        fecha_ferramentas()
        linhas.append(f"\n### 🤖 Claude · {buffer_hora}\n\n" + "\n\n".join(saida))
        buffer, buffer_hora = [], None

    for r in registros:
        tipo = r.get("type")
        if tipo not in ("user", "assistant") or r.get("isSidechain"):
            continue
        msg = r.get("message") or {}
        if tipo == "user" and so_resultado(msg.get("content")):
            continue
        txt, ferr = texto_de(msg.get("content"))
        n_tools += len(ferr)
        if not txt and not ferr:
            continue
        quando = (r.get("timestamp") or "")[11:16]
        if tipo == "user":
            descarrega()
            n_user += 1
            linhas.append(f"\n### 👤 Usuário · {quando}\n\n{corta(txt, LIMITE_TEXTO)}")
        else:
            if buffer_hora is None:
                buffer_hora = quando
            if txt:
                buffer.append(("txt", corta(txt, LIMITE_TEXTO)))
            buffer.extend(("tool", f) for f in ferr)
    descarrega()

    nome = re.sub(r"[^a-z0-9]+", "-", (titulo or caminho.stem[:8]).lower()).strip("-")[:48]
    destino = DESTINO / f"{inicio}-{nome}.md"
    cabecalho = (
        f"# {titulo or 'Sessão ' + caminho.stem[:8]}\n\n"
        f"**Sessão** `{caminho.stem}` · **início** {inicio} · **branch** `{ramo}`\n\n"
        f"{n_user} mensagens do usuário · {n_assist} respostas · {n_tools} chamadas de ferramenta\n\n"
        f"> Transcrição da sessão de trabalho. O raciocínio interno do modelo foi omitido e as\n"
        f"> saídas de ferramenta foram truncadas em {LIMITE_SAIDA} caracteres — o registro serve\n"
        f"> para acompanhar as decisões, não para reexecutar os comandos.\n\n---\n"
    )
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(cabecalho + "\n".join(linhas) + "\n")
    return destino, {"user": n_user, "assistant": n_assist, "tools": n_tools}

DESTINO.mkdir(exist_ok=True)
for f in sorted(ORIGEM.glob("*.jsonl")):
    d, st = exporta(f)
    print(f"{d}  ({d.stat().st_size/1024:.0f} KB)  {st['user']} prompts · {st['assistant']} respostas")
