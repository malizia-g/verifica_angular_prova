#!/usr/bin/env python3
"""
Server delle verifiche in rete locale — UGUALE PER TUTTE LE VERIFICHE.

Non contiene domande né chiavi: legge la cartella della verifica che gli passi
e si limita a
  - mandare agli studenti la pagina e (solo dopo l'accesso con il codice) le domande;
  - RICEVERE dati: accessi, salvataggi automatici, eventi (uscite dalla finestra…), consegne;
  - mostrare al docente chi è collegato e chi ha consegnato.
La chiave di correzione (chiave.json) NON viene mai inviata ai browser:
la correzione si fa dopo, con strumenti/correggi.py.

Uso:
    pip install flask                      (una volta sola, con internet)
    python server.py verifiche/TPSI/00.1.3-componenti-git --password segreta
Poi gli studenti aprono http://IP-DEL-DOCENTE:5000 e il docente http://localhost:5000/docente
"""
import argparse, copy, csv, hashlib, json, os, socket, threading, time, secrets
from flask import Flask, jsonify, request, send_from_directory, abort, Response

QUI = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(QUI, "docs")      # stessa pagina della versione online

ap = argparse.ArgumentParser(description="Server delle verifiche offline")
ap.add_argument("verifica", help="cartella della verifica (con domande.json e codici.csv)")
ap.add_argument("--porta", type=int, default=5000)
ap.add_argument("--password", default=None, help="password del pannello docente (se manca, ne genero una)")
args = ap.parse_args()

VER = os.path.abspath(args.verifica)
RAC = os.path.join(VER, "raccolta")
for d in ("", "salvataggi", "consegne"):
    os.makedirs(os.path.join(RAC, d), exist_ok=True)
PASSWORD = args.password or secrets.token_urlsafe(6)
LOCK = threading.Lock()

def leggi_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return default

def scrivi_json(p, dati):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(dati, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def aggiungi_riga(nome, dati):
    with open(os.path.join(RAC, nome), "a", encoding="utf-8") as f:
        f.write(json.dumps(dati, ensure_ascii=False) + "\n")

def leggi_csv(p):
    try:
        with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
    except FileNotFoundError: return []

# --- dati della verifica (solo lettura) ---
DOMANDE = leggi_json(os.path.join(VER, "domande.json"))
if not DOMANDE: raise SystemExit("Manca domande.json in " + VER)
CODICI = {r["codice"].strip().upper(): r for r in leggi_csv(os.path.join(VER, "codici.csv")) if r.get("codice")}
if not CODICI: raise SystemExit("Manca codici.csv (crealo con strumenti/crea_codici.py)")
LAB = {r["ip"].strip(): r.get("postazione", "").strip() for r in leggi_csv(os.path.join(VER, "laboratorio.csv")) if r.get("ip")}
DURATA_MIN = float(DOMANDE.get("durata_min", 60))
TOLLERANZA_S = 60          # secondi concessi dopo la scadenza
BATTITI = {}               # codice -> ultimo segnale dalla pagina

def numero(s): return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:6], 16)

def personale(cod, scenario):
    """Solo la versione dello studente: il suo scenario e una domanda per ogni coppia A/B."""
    P = copy.deepcopy(DOMANDE); n = len(DOMANDE.get("scenari") or [])
    if n:
        try: i = (int(scenario) - 1) % n
        except (TypeError, ValueError): i = numero(cod + "|scenario") % n
        P["scenari"] = [DOMANDE["scenari"][i]]; P["scenario_numero"] = i + 1
    for e in P.get("esercizi", []):
        if e.get("coppie"): e["coppie"] = [[c[numero(f"{cod}|{e['id']}|{k}") % len(c)]] for k, c in enumerate(e["coppie"])]
    return P

# --- stato delle sessioni (persistito, così un riavvio del server non perde niente) ---
STATO_P = os.path.join(RAC, "sessioni.json")
SESS = leggi_json(STATO_P, {})            # codice -> {token, ip, inizio, scadenza, consegnata, sblocchi, extra_min}
TOKEN = {s["token"]: c for c, s in SESS.items()}

def salva_stato(): scrivi_json(STATO_P, SESS)
def ora(): return time.time()
def ip_client(): return request.remote_addr or "?"

def sessione_da_token():
    dati = request.get_json(silent=True) or {}
    tok = dati.get("token") or request.args.get("token") or ""
    cod = TOKEN.get(tok)
    if not cod: abort(401)
    return cod, SESS[cod], dati

app = Flask(__name__, static_folder=None)

@app.after_request
def no_cache(r):
    r.headers["Cache-Control"] = "no-store"
    return r

# --- pagine statiche del motore (uguali per tutte le verifiche) ---
@app.get("/")
def pagina(): return send_from_directory(APP_DIR, "index.html")

@app.get("/app/<path:nome>")
def statici(nome):
    if nome in ("docente.html", "config.js"): abort(404)
    return send_from_directory(APP_DIR, nome)

# --- API studenti: accesso, domande, ricezione dati ---
@app.post("/api/accesso")
def accesso():
    dati = request.get_json(silent=True) or {}
    cod = str(dati.get("codice", "")).strip().upper()
    ip = ip_client()
    with LOCK:
        aggiungi_riga("accessi.jsonl", {"t": ora(), "codice": cod, "ip": ip, "postazione": LAB.get(ip, ""), "ua": request.headers.get("User-Agent", "")})
        if cod not in CODICI:
            return jsonify(errore="Codice non valido. Controlla il bigliettino o chiama il professore."), 403
        s = SESS.get(cod)
        if s and s.get("consegnata"):
            return jsonify(errore="Questa verifica è già stata consegnata."), 403
        if s and not s.get("sbloccato") and s.get("ip") != ip:
            aggiungi_riga("eventi.jsonl", {"t": ora(), "codice": cod, "ip": ip, "tipo": "accesso-bloccato", "dettaglio": "codice già usato da " + s.get("ip", "?")})
            return jsonify(errore="Codice già in uso su un'altra postazione. Chiama il professore."), 403
        if not s:
            t0 = ora()
            s = SESS[cod] = {"inizio": t0, "scadenza": t0 + DURATA_MIN * 60, "consegnata": False, "accessi": 0}
        if s.get("token"): TOKEN.pop(s["token"], None)
        s["token"] = secrets.token_urlsafe(16); TOKEN[s["token"]] = cod
        s["ip"] = ip; s["sbloccato"] = False; s["accessi"] = s.get("accessi", 0) + 1
        salva_stato()
        st = CODICI[cod]
        salvate = leggi_json(os.path.join(RAC, "salvataggi", cod + ".json"), {}).get("risposte", {})
        return jsonify(token=s["token"], nome=st.get("nome", ""), classe=st.get("classe", ""),
                       scenario=st.get("scenario", ""), seme=st.get("seme") or cod,
                       scadenza=s["scadenza"], ora_server=ora(), risposte=salvate, rientro=s["accessi"] > 1)

@app.get("/api/domande")
def domande():
    cod, s, _ = sessione_da_token()
    return jsonify(personale(cod, CODICI[cod].get("scenario")))

@app.post("/api/battito")
def battito():
    cod, s, _ = sessione_da_token()
    BATTITI[cod] = ora()
    return jsonify(ok=True)

@app.post("/api/salva")
def salva():
    cod, s, dati = sessione_da_token()
    with LOCK:
        if s.get("consegnata"): return jsonify(errore="Verifica già consegnata."), 409
        if ora() > s["scadenza"] + TOLLERANZA_S: return jsonify(errore="Tempo scaduto: valgono le risposte salvate fino alla scadenza."), 409
        scrivi_json(os.path.join(RAC, "salvataggi", cod + ".json"),
                    {"codice": cod, "t": ora(), "ip": ip_client(), "versione": dati.get("versione"), "risposte": dati.get("risposte", {}), "tempi": dati.get("tempi", {})})
        s["ultimo_salvataggio"] = ora(); s["ip_ultimo"] = ip_client()
        salva_stato()
    return jsonify(ok=True, scadenza=s["scadenza"], ora_server=ora())

@app.post("/api/evento")
def evento():
    cod, s, dati = sessione_da_token()
    with LOCK:
        aggiungi_riga("eventi.jsonl", {"t": ora(), "codice": cod, "ip": ip_client(), "tipo": str(dati.get("tipo", ""))[:40],
                                        "durata": dati.get("durata"), "dettaglio": str(dati.get("dettaglio", ""))[:200]})
        s["eventi"] = s.get("eventi", 0) + 1
        salva_stato()
    return jsonify(ok=True)

@app.post("/api/consegna")
def consegna():
    cod, s, dati = sessione_da_token()
    with LOCK:
        if s.get("consegnata"): return jsonify(ok=True, gia=True)
        rec = {"codice": cod, "t": ora(), "ip": ip_client(), "postazione": LAB.get(ip_client(), ""),
               "automatica": bool(dati.get("automatica")), "versione": dati.get("versione"),
               "risposte": dati.get("risposte", {}), "tempi": dati.get("tempi", {}), "inizio": s["inizio"]}
        if ora() > s["scadenza"] + TOLLERANZA_S:   # fuori tempo: valgono le risposte salvate prima della scadenza
            salv = leggi_json(os.path.join(RAC, "salvataggi", cod + ".json"), {})
            rec.update(automatica=True, fuori_tempo=True, risposte=salv.get("risposte", {}), tempi=salv.get("tempi", {}), versione=salv.get("versione") or rec["versione"])
            aggiungi_riga("eventi.jsonl", {"t": ora(), "codice": cod, "ip": ip_client(), "tipo": "consegna-fuori-tempo", "durata": round(ora() - s["scadenza"])})
        scrivi_json(os.path.join(RAC, "consegne", cod + ".json"), rec)
        s["consegnata"] = True; s["ora_consegna"] = rec["t"]
        salva_stato()
    return jsonify(ok=True)

# --- pannello docente ---
def docente_ok():
    a = request.authorization
    return a is not None and a.password == PASSWORD

def chiedi_password():
    return Response("Serve la password del docente.", 401, {"WWW-Authenticate": 'Basic realm="Docente"'})

@app.get("/docente")
def docente():
    if not docente_ok(): return chiedi_password()
    return send_from_directory(APP_DIR, "docente.html")

@app.get("/api/docente/stato")
def stato():
    if not docente_ok(): return chiedi_password()
    ip_usati = {}
    for c, s in SESS.items():
        if s.get("ip"): ip_usati.setdefault(s["ip"], []).append(c)
    righe = []
    for cod, st in CODICI.items():
        s = SESS.get(cod, {})
        avvisi = []
        if s.get("ip") and len(ip_usati.get(s["ip"], [])) > 1: avvisi.append("stesso PC di " + ", ".join(x for x in ip_usati[s["ip"]] if x != cod))
        post_att = st.get("postazione", "").strip(); post_ip = LAB.get(s.get("ip", ""), "")
        if post_att and post_ip and post_att != post_ip: avvisi.append(f"seduto a {post_ip} invece di {post_att}")
        if s.get("accessi", 0) > 1: avvisi.append(f"{s['accessi']} accessi")
        if s and not s.get("consegnata") and s.get("ultimo_salvataggio"):
            b = BATTITI.get(cod)
            if (not b and ora() - s["inizio"] > 60) or (b and s["ultimo_salvataggio"] - b > 90): avvisi.append("nessun segnale dai controlli (disattivati?)")
        if s and not s.get("consegnata") and ora() > s.get("scadenza", 1e18) + TOLLERANZA_S: avvisi.append("tempo scaduto, non ha consegnato")
        righe.append({"codice": cod, "nome": st.get("nome", ""), "classe": st.get("classe", ""), "scenario": st.get("scenario", ""),
                      "ip": s.get("ip", ""), "postazione": post_ip, "stato": "consegnata" if s.get("consegnata") else ("in corso" if s else "non entrato"),
                      "eventi": s.get("eventi", 0), "ultimo": s.get("ultimo_salvataggio"), "scadenza": s.get("scadenza"), "avvisi": avvisi})
    return jsonify(titolo=DOMANDE.get("titolo", ""), ora=ora(), righe=righe)

@app.post("/api/docente/sblocca")
def sblocca():
    if not docente_ok(): return chiedi_password()
    cod = (request.get_json(silent=True) or {}).get("codice", "").upper()
    with LOCK:
        if cod in SESS: SESS[cod]["sbloccato"] = True; salva_stato()
        aggiungi_riga("eventi.jsonl", {"t": ora(), "codice": cod, "tipo": "sbloccato-dal-docente"})
    return jsonify(ok=True)

@app.post("/api/docente/tempo")
def tempo():
    if not docente_ok(): return chiedi_password()
    d = request.get_json(silent=True) or {}
    cod = str(d.get("codice", "")).upper(); minuti = float(d.get("minuti", 5))
    with LOCK:
        if cod in SESS: SESS[cod]["scadenza"] = max(SESS[cod]["scadenza"], ora()) + minuti * 60; salva_stato()
        aggiungi_riga("eventi.jsonl", {"t": ora(), "codice": cod, "tipo": "tempo-aggiunto", "durata": minuti})
    return jsonify(ok=True)

def ip_locali():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ips.add(s.getsockname()[0]); s.close()
    except OSError: pass
    try:
        for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET): ips.add(i[4][0])
    except OSError: pass
    return sorted(i for i in ips if not i.startswith("127."))

if __name__ == "__main__":
    print("\n  Verifica:", DOMANDE.get("titolo", VER), f"· {len(CODICI)} codici · durata {DURATA_MIN:g} min")
    for i in ip_locali() or ["(IP non trovato: usa ipconfig)"]:
        print(f"  Studenti →  http://{i}:{args.porta}")
    print(f"  Docente  →  http://localhost:{args.porta}/docente   (utente: qualsiasi · password: {PASSWORD})")
    print("  Dati raccolti in:", RAC, "\n")
    app.run(host="0.0.0.0", port=args.porta, threaded=True)
