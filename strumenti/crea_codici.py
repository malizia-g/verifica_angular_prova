#!/usr/bin/env python3
"""
Crea i codici personali e i bigliettini da stampare.

Uso:
    python strumenti/crea_codici.py verifiche/00.1.3-componenti-git studenti.csv

studenti.csv: colonne  nome,classe  (facoltativa: postazione)
Se c'è la postazione, gli scenari (le "file") si alternano tra postazioni vicine.
Scrive nella cartella della verifica:
  codici.csv        (lo legge il server; NON consegnarlo agli studenti)
  bigliettini.html  (aprilo nel browser e stampalo, poi ritaglia)
Rilanciarlo crea codici NUOVI: fallo prima della verifica, non durante.
"""
import csv, html, json, os, re, secrets, sys

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # niente O/0, I/1/L: si confondono

def codice():
    p = lambda n: "".join(secrets.choice(ALFABETO) for _ in range(n))
    return p(3) + "-" + p(3)

def chiave_postazione(r):
    m = re.search(r"\d+", r.get("postazione", "") or "")
    return (0, int(m.group())) if m else (1, 0)

def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    ver, src = sys.argv[1], sys.argv[2]
    dom = json.load(open(os.path.join(ver, "domande.json"), encoding="utf-8"))
    n_scen = max(1, len(dom.get("scenari", [])))
    with open(src, encoding="utf-8-sig", newline="") as f:
        stud = [r for r in csv.DictReader(f) if (r.get("nome") or "").strip()]
    if any((r.get("postazione") or "").strip() for r in stud):
        stud.sort(key=chiave_postazione)
    usati, righe = set(), []
    for i, r in enumerate(stud):
        c = codice()
        while c in usati: c = codice()
        usati.add(c)
        righe.append({"codice": c, "nome": r["nome"].strip(), "classe": (r.get("classe") or "").strip(),
                      "scenario": str(i % n_scen + 1), "postazione": (r.get("postazione") or "").strip()})
    out = os.path.join(ver, "codici.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["codice", "nome", "classe", "scenario", "postazione"]); w.writeheader(); w.writerows(righe)
    carte = "".join(
        f'<div class="b"><div class="n">{html.escape(r["nome"])}</div><div class="c">{html.escape(r["classe"])}'
        f'{" · postazione " + html.escape(r["postazione"]) if r["postazione"] else ""}</div>'
        f'<div class="k">{r["codice"]}</div><div class="i">Apri il browser su: ______________________</div></div>' for r in righe)
    pagina = f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Bigliettini · {html.escape(dom.get('titolo',''))}</title>
<style>body{{font-family:Arial,sans-serif;margin:10mm}} .g{{display:grid;grid-template-columns:repeat(3,1fr);gap:0}}
.b{{border:1px dashed #888;padding:6mm 5mm;break-inside:avoid}} .n{{font-weight:700;font-size:13pt}} .c{{font-size:10pt;color:#444}}
.k{{font:700 22pt Consolas,monospace;letter-spacing:2px;margin:3mm 0}} .i{{font-size:9pt;color:#444}}
h1{{font-size:12pt}} @media print{{h1{{display:none}}}}</style></head><body>
<h1>{html.escape(dom.get('titolo',''))} — {len(righe)} bigliettini (stampa con Ctrl+P e ritaglia)</h1><div class="g">{carte}</div></body></html>"""
    open(os.path.join(ver, "bigliettini.html"), "w", encoding="utf-8").write(pagina)
    print(f"{len(righe)} codici in {out}\nBigliettini: {os.path.join(ver, 'bigliettini.html')}")

if __name__ == "__main__":
    main()
