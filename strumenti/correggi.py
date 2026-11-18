#!/usr/bin/env python3
"""
Corregge una verifica a server spento (o anche mentre gira: legge solo i file).

Uso:
    python strumenti/correggi.py verifiche/00.1.3-componenti-git

Legge domande.json, chiave.json, codici.csv e la cartella raccolta/.
Se esiste aperte.csv (colonne: codice + una colonna per ogni domanda aperta, es. d1,d2,d3)
ne usa i punti; altrimenti le domande aperte restano da correggere.
Scrive in risultati/:
  risultati.csv            una riga per studente, pronta da importare nel foglio Google
  aperte.csv               modello da riempire con i punti delle domande aperte
  report.html              dettaglio per studente, sospetti di copiatura, risposte aperte raggruppate
"""
import csv, html, json, math, os, re, sys, time
from collections import Counter, defaultdict

def J(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return d

def mezzi(x): return math.floor(x * 2 + 1e-9) / 2

def lcs(a, b, uguale):
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            m[i + 1][j + 1] = m[i][j] + 1 if uguale(a[i], b[j]) else max(m[i][j + 1], m[i + 1][j])
    return m[-1][-1]

def corrisponde(risp, el): return risp in el if isinstance(el, list) else risp == el

def voto_passaggio(risp, k):
    best, extra_best = 0.0, []
    for alt in k["alternative"]:
        seq, peso = alt["seq"], alt.get("peso", 1)
        if alt.get("ordinato", True): m = lcs(risp, seq, corrisponde)
        else: m = sum(1 for el in seq if any(corrisponde(r, el) for r in risp))
        v = mezzi(k["punti"] * m / len(seq) * peso)
        if v >= best:
            ok = set(k.get("opzionali", [])) | {x for el in seq for x in (el if isinstance(el, list) else [el])}
            best, extra_best = v, [r for r in risp if r not in ok]
    return best, extra_best

def parole(t): return set(w for w in re.findall(r"\w+", (t or "").lower()) if len(w) > 2)

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    ver = sys.argv[1]; rac = os.path.join(ver, "raccolta"); out = os.path.join(ver, "risultati"); os.makedirs(out, exist_ok=True)
    D = J(os.path.join(ver, "domande.json")); K = J(os.path.join(ver, "chiave.json"))
    with open(os.path.join(ver, "codici.csv"), encoding="utf-8-sig", newline="") as f: COD = {r["codice"]: r for r in csv.DictReader(f)}
    ES = {e["id"]: e for e in D["esercizi"]}
    testo_striscia = {e["id"]: {s["id"]: s["t"] for s in e.get("strisce", [])} for e in D["esercizi"]}
    domande_aperte = [q for e in D["esercizi"] if e["tipo"] == "aperte" for c in e["coppie"] for q in c]
    testo_q = {q["id"]: q["t"] for e in D["esercizi"] if e["tipo"] in ("crocette", "aperte") for c in e["coppie"] for q in c}
    n_aperte = max([len(e["coppie"]) for e in D["esercizi"] if e["tipo"] == "aperte"] or [0])

    aperte_p = {}
    pa = os.path.join(out, "aperte.csv")
    if os.path.exists(pa):
        with open(pa, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f): aperte_p[r["codice"]] = r

    eventi = defaultdict(list)
    try:
        for riga in open(os.path.join(rac, "eventi.jsonl"), encoding="utf-8"):
            e = json.loads(riga); eventi[e.get("codice", "")].append(e)
    except FileNotFoundError: pass

    sub = lambda s, P: re.sub(r"%(\w+)%", lambda m: str(P.get(m.group(1), m.group(0))), s)
    risultati, dett = [], {}
    for cod, st in COD.items():
        rec = J(os.path.join(rac, "consegne", cod + ".json"))
        stato = "consegnata"
        if not rec:
            rec = J(os.path.join(rac, "salvataggi", cod + ".json"))
            stato = "NON consegnata (ultimo salvataggio)" if rec else "assente"
        if not rec:
            risultati.append(dict(codice=cod, nome=st["nome"], classe=st["classe"], stato=stato)); continue
        R, Vv = rec.get("risposte", {}), rec.get("versione") or {}
        P = D["scenari"][(Vv.get("scenario") or 1) - 1] if D.get("scenari") else {}
        row = dict(codice=cod, nome=st["nome"], classe=st["classe"], stato=stato, scenario=Vv.get("scenario", ""))
        d = dett[cod] = dict(st=st, rec=rec, P=P, righe=[], errori=set())
        tot, da_correggere = 0.0, False
        for eid, k in K.items():
            if not isinstance(k, dict) or "tipo" not in k: continue
            r = R.get(eid, {})
            if k["tipo"] == "sequenze":
                s_es = 0
                for pid, kp in k["passaggi"].items():
                    v, extra = voto_passaggio(r.get(pid, []), kp); s_es += v; row[f"{eid} {pid}"] = v
                    d["righe"].append((f"{eid} {pid}", v, kp["punti"], " → ".join(sub(testo_striscia[eid].get(x, x), P) for x in r.get(pid, [])) or "—",
                                       "in più: " + ", ".join(sub(testo_striscia[eid].get(x, x), P) for x in extra) if extra else ""))
                    if v < kp["punti"] and r.get(pid): d["errori"].add((eid, pid, tuple(r.get(pid))))
            elif k["tipo"] == "riquadri":
                s_es = 0
                for rq, ok in k["riquadri"].items():
                    a = r.get(rq, ""); v = k.get("punti_per_riquadro", 1) if a == ok else 0; s_es += v; row[f"{eid} [{rq}]"] = v
                    d["righe"].append((f"{eid} [{rq}]", v, k.get("punti_per_riquadro", 1), sub(testo_striscia[eid].get(a, "—"), P), "" if v else "giusta: " + sub(testo_striscia[eid][ok], P)))
                    if a and a != ok: d["errori"].add((eid, rq, a))
            elif k["tipo"] == "crocette":
                s_es = 0; ppd = k.get("punti_per_domanda", 1)
                for i, qid in enumerate((Vv.get("scelte") or {}).get(eid, [])):
                    a = r.get(qid, ""); v = ppd if a == k["risposte"].get(qid) else 0; s_es += v; row[f"{eid} d{i+1}"] = v
                    d["righe"].append((f"{eid} d{i+1} ({qid})", v, ppd, "risposta data" if a else "vuota", ""))
                    if a and v == 0: d["errori"].add((eid, qid, a))
            elif k["tipo"] == "aperte":
                s_es = 0; ap = aperte_p.get(cod, {})
                for i, qid in enumerate((Vv.get("scelte") or {}).get(eid, [])):
                    pt = ap.get(f"d{i+1}", "")
                    try: v = float(str(pt).replace(",", ".")); s_es += v
                    except ValueError: v = ""; da_correggere = True
                    row[f"{eid} d{i+1}"] = v
            else: continue
            row[eid] = round(s_es, 2); tot += s_es
        row["totale"] = round(tot, 2); row["voto"] = round(tot / 3, 2)
        if da_correggere: row["note"] = "domande aperte da correggere (aperte.csv)"
        ev = eventi.get(cod, []); c = Counter(e["tipo"] for e in ev)
        fuori = sum((e.get("durata") or 0) for e in ev if e["tipo"] in ("scheda-nascosta", "finestra-non-attiva"))
        row["eventi"] = sum(c.values()); row["secondi fuori"] = fuori
        row["dettaglio eventi"] = ", ".join(f"{t}×{n}" for t, n in c.most_common())
        row["postazione/IP"] = (rec.get("postazione") or "") + " " + (rec.get("ip") or "")
        tempi = rec.get("tempi", {}); durata = rec.get("t", 0) - rec.get("inizio", rec.get("t", 0))
        if tempi and durata > 300:
            tardi = sum(1 for x in tempi.values() if x.get("p", 0) > durata - 120)
            if tardi / len(tempi) > .5: row["segnalazioni"] = f"{tardi} risposte su {len(tempi)} date negli ultimi 2 minuti"
        risultati.append(row)

    # sospetti di copiatura: stessi errori, testi aperti simili
    coppie = []
    cods = [c for c in dett]
    for i in range(len(cods)):
        for j in range(i + 1, len(cods)):
            a, b = dett[cods[i]], dett[cods[j]]
            comuni = a["errori"] & b["errori"]
            simili = []
            ra, rb = a["rec"]["risposte"], b["rec"]["risposte"]
            for e in D["esercizi"]:
                if e["tipo"] != "aperte": continue
                for qid, ta in (ra.get(e["id"]) or {}).items():
                    tb = (rb.get(e["id"]) or {}).get(qid)
                    if tb:
                        A, B = parole(ta), parole(tb)
                        if len(A) >= 8 and len(B) >= 8 and len(A & B) / len(A | B) >= .6: simili.append(qid)
            if len(comuni) >= 3 or simili:
                coppie.append((len(comuni) + 3 * len(simili), cods[i], cods[j], len(comuni), simili))
    coppie.sort(reverse=True)
    sospetti = defaultdict(list)
    for _, x, y, n, s in coppie:
        sospetti[x].append(COD[y]["nome"]); sospetti[y].append(COD[x]["nome"])
    for r in risultati:
        if r["codice"] in sospetti: r["simile a"] = ", ".join(sospetti[r["codice"]])

    # risultati.csv
    campi = []
    for r in risultati:
        for k in r:
            if k not in campi: campi.append(k)
    with open(os.path.join(out, "risultati.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campi, delimiter=";"); w.writeheader()
        for r in risultati: w.writerow({k: (str(v).replace(".", ",") if isinstance(v, float) else v) for k, v in r.items()})
    # modello aperte.csv
    if not os.path.exists(os.path.join(out, "aperte.csv")):
        with open(os.path.join(out, "aperte.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(["codice", "nome"] + [f"d{i+1}" for i in range(n_aperte)])
            for c in dett: w.writerow([c, COD[c]["nome"]] + [""] * n_aperte)

    # report.html
    E = html.escape
    h = [f"<!doctype html><html lang='it'><head><meta charset='utf-8'><title>Report · {E(D['titolo'])}</title><style>"
         "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;color:#18203a;max-width:1100px}table{border-collapse:collapse;width:100%;margin:8px 0}"
         "td,th{border-bottom:1px solid #dde;padding:4px 6px;text-align:left;vertical-align:top;font-size:13px}th{background:#f4f5f9}"
         ".ko{color:#c92a2a}.ok{color:#2b8a3e}.w{color:#d9480f;font-weight:600}h2{margin-top:28px}details{margin:6px 0}code{background:#eef1f8;padding:1px 4px}"
         ".ans{white-space:pre-wrap;background:#f7f8fb;border-left:3px solid #3b2fc9;padding:6px 10px;margin:4px 0}</style></head><body>",
         f"<h1>{E(D['titolo'])}</h1><p>Generato il {time.strftime('%d/%m/%Y %H:%M')} · {len(dett)} consegne su {len(COD)} codici.</p>"]
    h.append("<h2>Sospetti di copiatura</h2>")
    if coppie:
        h.append("<table><tr><th>Studente</th><th>Studente</th><th>Stessi errori</th><th>Domande aperte molto simili</th><th>Postazioni</th></tr>")
        for _, x, y, n, s in coppie:
            px = (dett[x]["rec"].get("postazione") or dett[x]["rec"].get("ip", "")); py = (dett[y]["rec"].get("postazione") or dett[y]["rec"].get("ip", ""))
            h.append(f"<tr><td>{E(COD[x]['nome'])}</td><td>{E(COD[y]['nome'])}</td><td class='w'>{n}</td><td>{E(', '.join(s))}</td><td>{E(str(px))} · {E(str(py))}</td></tr>")
        h.append("</table><p>«Stessi errori» conta le risposte <b>sbagliate in modo identico</b> (stessa crocetta sbagliata, stessa striscia sbagliata, stessa sequenza sbagliata). Le risposte giuste uguali non contano.</p>")
    else: h.append("<p>Nessuna coppia sospetta.</p>")
    h.append("<h2>Riepilogo</h2><table><tr><th>Studente</th><th>Stato</th><th>Totale</th><th>Voto</th><th>Eventi</th><th>Secondi fuori</th><th>Segnalazioni</th></tr>")
    for r in sorted(risultati, key=lambda r: r["nome"]):
        h.append(f"<tr><td>{E(r['nome'])}</td><td>{E(r['stato'])}</td><td>{r.get('totale','')}</td><td>{r.get('voto','')}</td>"
                 f"<td class='{'w' if r.get('eventi',0)>=3 else ''}'>{E(str(r.get('dettaglio eventi','')))}</td><td>{r.get('secondi fuori','')}</td>"
                 f"<td class='w'>{E(' · '.join(x for x in [r.get('segnalazioni',''), ('simile a ' + r['simile a']) if r.get('simile a') else ''] if x))}</td></tr>")
    h.append("</table><h2>Domande aperte, raggruppate per domanda</h2><p>Scrivi i punti in <code>aperte.csv</code> (colonne d1, d2, d3 = prima, seconda, terza domanda aperta che lo studente ha avuto), poi rilancia <code>correggi.py</code>.</p>")
    tracce = next((k.get("tracce", {}) for k in K.values() if isinstance(k, dict) and k.get("tipo") == "aperte"), {})
    for q in domande_aperte:
        blocchi = []
        for c, d in dett.items():
            for e in D["esercizi"]:
                if e["tipo"] == "aperte" and q["id"] in ((d["rec"].get("versione") or {}).get("scelte") or {}).get(e["id"], []):
                    pos = d["rec"]["versione"]["scelte"][e["id"]].index(q["id"]) + 1
                    t = (d["rec"]["risposte"].get(e["id"]) or {}).get(q["id"], "")
                    blocchi.append(f"<p><b>{E(COD[c]['nome'])}</b> (colonna d{pos})</p><div class='ans'>{E(t) or '<i>vuota</i>'}</div>")
        if blocchi:
            h.append(f"<details open><summary><b>{q['id']}</b> · {re.sub('<[^>]+>', '', sub(q['t'], {}))[:160]}</summary>"
                     f"<p><i>Traccia: {E(tracce.get(q['id'], ''))}</i></p>{''.join(blocchi)}</details>")
    h.append("<h2>Dettaglio per studente</h2>")
    for c, d in sorted(dett.items(), key=lambda x: x[1]["st"]["nome"]):
        h.append(f"<details><summary><b>{E(d['st']['nome'])}</b> · scenario {d['rec'].get('versione',{}).get('scenario','')}</summary><table><tr><th>Voce</th><th>Punti</th><th>Max</th><th>Risposta</th><th>Nota</th></tr>")
        for voce, v, mx, risp, nota in d["righe"]:
            h.append(f"<tr><td>{E(voce)}</td><td class='{'ok' if v == mx else 'ko'}'>{v}</td><td>{mx}</td><td>{E(risp)}</td><td>{E(nota)}</td></tr>")
        evs = eventi.get(c, [])
        if evs:
            h.append("<tr><th colspan='5'>Eventi</th></tr>" + "".join(
                f"<tr><td>{time.strftime('%H:%M:%S', time.localtime(e['t']))}</td><td colspan='4'>{E(e['tipo'])}{(' · ' + str(e['durata']) + ' s') if e.get('durata') else ''}</td></tr>" for e in evs))
        h.append("</table></details>")
    h.append("</body></html>")
    open(os.path.join(out, "report.html"), "w", encoding="utf-8").write("".join(h))
    print(f"{len(dett)} consegne corrette · {len(coppie)} coppie sospette\n  {os.path.join(out, 'risultati.csv')}\n  {os.path.join(out, 'report.html')}\n  {os.path.join(out, 'aperte.csv')} (da riempire per le domande aperte)")

if __name__ == "__main__":
    main()
