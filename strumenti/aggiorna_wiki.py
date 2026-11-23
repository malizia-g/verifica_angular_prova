#!/usr/bin/env python3
"""
Scrive la pagina wiki "Registro verifiche" partendo da verifiche.config.json.
Le verifiche sono divise per materia e anno di corso (TPSI - 3, TPSI - 4, …).
Per ogni verifica: foglio Google (risposte e correzione), pannello docente e pagina studenti.

Uso:
    python strumenti/aggiorna_wiki.py <cartella-della-wiki>

Lo lancia da solo il workflow .github/workflows/wiki.yml a ogni modifica del config.
Riscrive solo Registro-verifiche.md; crea Home.md solo se non esiste.
"""
import json, os, re, sys
from collections import defaultdict

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = "Registro-verifiche.md"


def anno(classe):
    m = re.match(r"\s*(\d)", classe or "")
    return m.group(1) if m else "?"


def ordina_materia(m):
    return (m == "?", m)


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    wiki = sys.argv[1]
    C = json.load(open(os.path.join(RADICE, "verifiche.config.json"), encoding="utf-8"))
    sito = C["sito"].rstrip("/") + "/docs/"

    gruppi = defaultdict(list)
    for chiave, v in C.get("verifiche", {}).items():
        materia, _, cartella = chiave.partition("/")
        gruppi[(materia or "?", anno(v.get("classe")))].append((cartella, v))

    righe = [
        "# Registro verifiche",
        "",
        "Pagina generata da `strumenti/aggiorna_wiki.py` a partire da `verifiche.config.json`: "
        "non modificarla a mano, si riscrive a ogni aggiornamento del config.",
        "",
        f"- Pagina studenti generica (trova da sola la verifica aperta): {sito}",
        f"- Pannello docente: {sito}docente.html",
        f"- Foglio \"Registro verifiche\": https://docs.google.com/spreadsheets/d/{C['registro_foglio']}/edit",
        "",
    ]
    indice = []
    corpo = []
    for (materia, a) in sorted(gruppi, key=lambda g: (ordina_materia(g[0]), g[1])):
        titolo = f"{materia} - {a}"
        ancora = re.sub(r"[^a-z0-9 -]", "", titolo.lower()).replace(" ", "-")
        indice.append(f"- [{titolo}](#{ancora})")
        corpo += [f"## {titolo}", "",
                  "| Data | Classe | Verifica | Foglio correzioni | Docente | Studenti |",
                  "|---|---|---|---|---|---|"]
        elenco = sorted(gruppi[(materia, a)], key=lambda x: (x[1].get("creata", ""), x[0]), reverse=True)
        for cartella, v in elenco:
            f = v["foglio"]
            nome = (v.get("titolo") or cartella).replace("|", "/")
            corpo.append(
                f"| {v.get('creata', '')} | {v.get('classe', '')} | {nome} "
                f"| [foglio](https://docs.google.com/spreadsheets/d/{f}/edit) "
                f"| [pannello]({sito}docente.html?v={f}) "
                f"| [pagina]({sito}?v={f}) |")
        corpo.append("")

    testo = "\n".join(righe + indice + [""] + corpo)
    os.makedirs(wiki, exist_ok=True)
    open(os.path.join(wiki, PAGINA), "w", encoding="utf-8").write(testo)
    home = os.path.join(wiki, "Home.md")
    if not os.path.exists(home):
        open(home, "w", encoding="utf-8").write("# Verifiche online\n\n- [[Registro verifiche|Registro-verifiche]]\n")
    print(f"Scritto {PAGINA}: {sum(len(x) for x in gruppi.values())} verifiche in {len(gruppi)} gruppi")


if __name__ == "__main__":
    main()
