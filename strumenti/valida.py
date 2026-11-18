#!/usr/bin/env python3
"""
Controlla domande.json e chiave.json di una verifica prima di pubblicarla.

Uso:
    python strumenti/valida.py verifiche/TPSI/00.1.3-componenti-git

Esce con codice 1 se trova ERRORI; gli AVVISI non bloccano.
"""
import json, os, re, sys

TIPI = {"sequenze", "riquadri", "crocette", "aperte"}

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    ver = sys.argv[1]
    D = json.load(open(os.path.join(ver, "domande.json"), encoding="utf-8"))
    K = json.load(open(os.path.join(ver, "chiave.json"), encoding="utf-8"))
    err, avv = [], []
    E = lambda m: err.append(m)
    A = lambda m: avv.append(m)

    for k in ("titolo", "durata_min", "esercizi"):
        if k not in D: E(f"domande.json: manca '{k}'")
    scen = D.get("scenari") or []
    if not scen: A("nessuno scenario: tutti avranno gli stessi nomi (meno protezione dalla copiatura)")
    elif len(scen) < 3: A(f"solo {len(scen)} scenari: con meno di 3 due vicini possono avere la stessa versione")
    chiavi_scen = [set(s) for s in scen]

    def segnaposti(testo, dove):
        for p in re.findall(r"%(\w+)%", str(testo)):
            for i, ks in enumerate(chiavi_scen):
                if p not in ks: E(f"{dove}: %{p}% non esiste nello scenario {i+1}")

    ids_es, ids_q, tot = set(), set(), 0
    for e in D.get("esercizi", []):
        eid = e.get("id"); dove = f"esercizio {eid}"
        if eid in ids_es: E(f"{dove}: id ripetuto")
        ids_es.add(eid)
        if e.get("tipo") not in TIPI: E(f"{dove}: tipo '{e.get('tipo')}' sconosciuto"); continue
        tot += float(e.get("punti", 0))
        segnaposti(e.get("testo", ""), dove)
        k = K.get(eid)
        if not k: E(f"{dove}: manca in chiave.json"); continue
        if k.get("tipo") != e["tipo"]: E(f"{dove}: tipo diverso in chiave.json")

        if e["tipo"] in ("sequenze", "riquadri"):
            strisce = {s["id"] for s in e.get("strisce", [])}
            if len(strisce) != len(e.get("strisce", [])): E(f"{dove}: id di strisce ripetuti")
            for s in e.get("strisce", []): segnaposti(s.get("t"), f"{dove} striscia {s.get('id')}")

        if e["tipo"] == "sequenze":
            pas = e.get("passaggi", [])
            if len(e.get("stati", [])) != len(pas) + 1: E(f"{dove}: servono {len(pas)+1} stati per {len(pas)} passaggi")
            for st in e.get("stati", []):
                for c in ("note", "git", "term"): segnaposti(st.get(c, ""), f"{dove} stato {st.get('l')}")
            kp = k.get("passaggi", {}); punti_pas = 0
            for p in pas:
                if p["id"] not in kp: E(f"{dove}: passaggio {p['id']} senza soluzione"); continue
                punti_pas += float(p.get("punti", 0))
                for alt in kp[p["id"]].get("alternative", []):
                    for el in alt.get("seq", []):
                        for x in (el if isinstance(el, list) else [el]):
                            if x not in strisce: E(f"{dove} {p['id']}: striscia {x} non esiste")
                for x in kp[p["id"]].get("opzionali", []):
                    if x not in strisce: E(f"{dove} {p['id']}: striscia opzionale {x} non esiste")
            if abs(punti_pas - float(e.get("punti", 0))) > 1e-6: A(f"{dove}: punti dei passaggi ({punti_pas:g}) ≠ punti esercizio ({e.get('punti')})")
            usate = {x for p in kp.values() for a in p.get("alternative", []) for el in a.get("seq", []) for x in (el if isinstance(el, list) else [el])}
            if len(strisce - usate) < 3: A(f"{dove}: meno di 3 strisce distrattore")

        elif e["tipo"] == "riquadri":
            buchi = [b for f in e.get("file", []) for b in re.findall(r"\[\[(\w+)\]\]", f.get("codice", ""))]
            for f in e.get("file", []): segnaposti(f.get("codice", ""), f"{dove} file {f.get('nome')}"); segnaposti(f.get("nome", ""), dove)
            if len(set(buchi)) != len(buchi): E(f"{dove}: riquadri con lo stesso numero")
            kr = k.get("riquadri", {})
            for b in buchi:
                if b not in kr: E(f"{dove}: riquadro [[{b}]] senza soluzione")
                elif kr[b] not in strisce: E(f"{dove}: soluzione del riquadro {b} ({kr[b]}) non è tra le strisce")
            for b in kr:
                if b not in buchi: E(f"{dove}: in chiave c'è il riquadro {b} che nel codice non esiste")
            if len(strisce) < len(buchi) + 4: A(f"{dove}: pochi distrattori ({len(strisce) - len(buchi)})")

        elif e["tipo"] in ("crocette", "aperte"):
            for i, c in enumerate(e.get("coppie", [])):
                if len(c) < 2: A(f"{dove} coppia {i+1}: una sola variante (meglio A e B)")
                for q in c:
                    qid = q.get("id"); d2 = f"{dove} domanda {qid}"
                    if qid in ids_q: E(f"{d2}: id ripetuto")
                    ids_q.add(qid); segnaposti(q.get("t"), d2)
                    if e["tipo"] == "crocette":
                        ops = q.get("opzioni", [])
                        if len(ops) < 3: E(f"{d2}: servono almeno 3 opzioni")
                        oid = [o["id"] for o in ops]
                        if len(set(oid)) != len(oid): E(f"{d2}: id di opzioni ripetuti")
                        if any(re.fullmatch(r"[a-dA-D1-4]", x) for x in oid): E(f"{d2}: id opzioni troppo prevedibili (usa id opachi tipo o3f9a)")
                        for o in ops: segnaposti(o.get("t"), d2)
                        giusta = k.get("risposte", {}).get(qid)
                        if giusta is None: E(f"{d2}: manca la risposta in chiave")
                        elif giusta not in oid: E(f"{d2}: la risposta {giusta} non è tra le opzioni")
                        lun = [len(re.sub(r"<[^>]+>", "", o["t"])) for o in ops]
                        if giusta in oid and lun[oid.index(giusta)] == max(lun) and max(lun) > 1.6 * sorted(lun)[-2]:
                            A(f"{d2}: la risposta giusta è molto più lunga delle altre (si indovina)")
                    else:
                        if qid not in k.get("tracce", {}): E(f"{d2}: manca la traccia di correzione")

    if abs(tot - 30) > 1e-6: A(f"totale punti {tot:g} (le verifiche di solito sono da 30: voto = punti ÷ 3)")
    for m in err: print("ERRORE ", m)
    for m in avv: print("avviso ", m)
    print(f"\n{len(D.get('esercizi', []))} esercizi · {tot:g} punti · {len(scen)} scenari · {len(err)} errori · {len(avv)} avvisi")
    sys.exit(1 if err else 0)

if __name__ == "__main__":
    main()
