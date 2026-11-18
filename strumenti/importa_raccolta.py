#!/usr/bin/env python3
"""
Versione online: trasforma raccolta.json (scaricato dal pannello docente) nella cartella raccolta/
che correggi.py si aspetta. Dopo puoi correggere come in laboratorio.

Uso:
    python strumenti/importa_raccolta.py verifiche/00.1.3-componenti-git raccolta.json
    python strumenti/correggi.py verifiche/00.1.3-componenti-git

Accetta anche i VALORI GREZZI delle schede del foglio, come li legge Claude con il connettore Google Sheets:
    {"codici": [[intestazione], [riga], ...], "sessioni": [...], "risposte": [...], "eventi": [...]}

Riscrive anche codici.csv con i codici presenti nel foglio Google (così nome e classe coincidono).
"""
import csv, json, os, shutil, sys

NUMERI = {"t", "inizio", "scadenza", "ora_consegna", "accessi", "eventi", "ultimo_salvataggio", "durata"}

def grezzi_a_raccolta(R):
    """Se R contiene le schede come tabelle (liste di righe), le trasforma nel formato di 'esporta'."""
    if not (isinstance(R.get("sessioni"), list) and R["sessioni"] and isinstance(R["sessioni"][0], list)): return R
    def tab(nome):
        t = R.get(nome) or []
        if not t: return []
        h = t[0]; out = []
        for riga in t[1:]:
            if not riga or not str(riga[0]).strip(): continue
            o = {k: (riga[j] if j < len(riga) else "") for j, k in enumerate(h)}
            for k in NUMERI & o.keys():
                try: o[k] = float(str(o[k]).replace(",", ".")) if str(o[k]).strip() != "" else None
                except ValueError: pass
            if "codice" in o: o["codice"] = str(o["codice"]).strip().upper()
            out.append(o)
        return out
    risp = tab("risposte")
    for r in risp:
        for k in ("versione", "risposte", "tempi"):
            try: r[k] = json.loads(r.get(k) or "{}")
            except ValueError: r[k] = {}
    return {"codici": tab("codici"), "sessioni": tab("sessioni"), "risposte": risp, "eventi": tab("eventi")}

def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    ver, src = sys.argv[1], sys.argv[2]
    R = grezzi_a_raccolta(json.load(open(src, encoding="utf-8")))
    rac = os.path.join(ver, "raccolta")
    if os.path.isdir(rac): shutil.rmtree(rac)
    for d in ("salvataggi", "consegne"): os.makedirs(os.path.join(rac, d))

    sess = {s["codice"]: s for s in R.get("sessioni", [])}
    n_cons = n_salv = 0
    for r in R.get("risposte", []):
        cod = r["codice"]; s = sess.get(cod, {})
        rec = {"codice": cod, "t": r.get("t"), "ip": "", "postazione": "", "versione": r.get("versione") or {},
               "risposte": r.get("risposte") or {}, "tempi": r.get("tempi") or {}, "inizio": s.get("inizio")}
        if str(r.get("stato")) == "consegnata":
            rec["automatica"] = str(r.get("automatica")).lower() in ("true", "vero", "1")
            json.dump(rec, open(os.path.join(rac, "consegne", cod + ".json"), "w", encoding="utf-8"), ensure_ascii=False); n_cons += 1
        json.dump(rec, open(os.path.join(rac, "salvataggi", cod + ".json"), "w", encoding="utf-8"), ensure_ascii=False); n_salv += 1

    with open(os.path.join(rac, "eventi.jsonl"), "w", encoding="utf-8") as f:
        for e in R.get("eventi", []):
            f.write(json.dumps({"t": e.get("t"), "codice": str(e.get("codice", "")).upper(), "ip": e.get("dispositivo", ""),
                                "tipo": e.get("tipo", ""), "durata": e.get("durata") if e.get("durata") != "" else None,
                                "dettaglio": e.get("dettaglio", "")}, ensure_ascii=False) + "\n")
    json.dump({c: {k: v for k, v in s.items()} for c, s in sess.items()},
              open(os.path.join(rac, "sessioni.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    cod = R.get("codici") or []
    if cod:
        with open(os.path.join(ver, "codici.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["codice", "nome", "classe", "scenario", "postazione"], extrasaction="ignore")
            w.writeheader()
            for r in cod: w.writerow({k: r.get(k, "") for k in w.fieldnames})
    print(f"{n_cons} consegne, {n_salv} salvataggi, {len(R.get('eventi', []))} eventi → {rac}")
    print(f"Ora: python strumenti/correggi.py {ver}")

if __name__ == "__main__":
    main()
