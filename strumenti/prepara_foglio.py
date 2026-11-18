#!/usr/bin/env python3
"""
Versione online: prepara il contenuto del Google Sheet di una verifica.

Uso:
    python strumenti/prepara_foglio.py verifiche/TPSI/00.1.3-componenti-git > foglio.json

Scrive su stdout un JSON {nome_scheda: [[riga], ...]} con le schede
impostazioni, codici, domande, sessioni, risposte, eventi — pronto da scrivere nel foglio
(ogni scheda dalla cella A1). La chiave di correzione NON entra nel foglio.
Le domande sono spezzate in pezzi da 40.000 caratteri (limite di una cella: 50.000).
"""
import csv, json, os, sys

INTESTAZIONI = {
    "sessioni": ["codice", "token", "dispositivo", "inizio", "scadenza", "consegnata", "ora_consegna", "accessi", "eventi", "ultimo_salvataggio", "sbloccato", "browser"],
    "risposte": ["codice", "t", "stato", "automatica", "fuori_tempo", "versione", "risposte", "tempi"],
    "eventi":   ["t", "ora", "codice", "tipo", "durata", "dettaglio", "dispositivo"],
}

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    ver = sys.argv[1]
    D = json.load(open(os.path.join(ver, "domande.json"), encoding="utf-8"))
    testo = json.dumps(D, ensure_ascii=False, separators=(",", ":"))
    pezzi = [testo[i:i + 40000] for i in range(0, len(testo), 40000)]
    with open(os.path.join(ver, "codici.csv"), encoding="utf-8-sig", newline="") as f:
        cod = [[r["codice"], r["nome"], r.get("classe", ""), str(r.get("scenario", "")), r.get("postazione", "")] for r in csv.DictReader(f)]
    out = {
        "impostazioni": [["chiave", "valore"], ["aperta", "NO"], ["durata_min", D.get("durata_min", 60)]],
        "codici": [["codice", "nome", "classe", "scenario", "postazione"]] + cod,
        "domande": [["json"]] + [[p] for p in pezzi],
    }
    out.update({k: [v] for k, v in INTESTAZIONI.items()})
    json.dump(out, sys.stdout, ensure_ascii=False)

if __name__ == "__main__":
    main()
