# Verifiche nel browser: online e in laboratorio

Una sola pagina per gli studenti (`docs/index.html`) e un solo pannello docente (`docs/docente.html`), con due modi di funzionare:

| | Online | Laboratorio |
|---|---|---|
| Pagina | GitHub Pages (cartella `docs/`) | `server.py` sul PC del docente |
| "Server" | **Un solo** Apps Script per tutte le verifiche | Flask, internet staccato |
| Dati | Un Google Sheet per verifica | `verifiche/.../raccolta/` |
| Correzione | `strumenti/correggi.py` | uguale |

## Struttura

```
docs/                     ← sito pubblicato (Settings → Pages → main, /docs)
  index.html              ← pagina studenti
  docente.html            ← pannello docente
  config.js               ← URL dell'Apps Script (l'unica riga da cambiare)
apps-script/Codice.gs     ← server online unico (collegato al foglio "Registro verifiche")
server.py                 ← server di laboratorio
strumenti/
  valida.py               ← controlla domande.json e chiave.json
  crea_codici.py          ← codici personali + bigliettini
  prepara_foglio.py       ← contenuto del Google Sheet di una verifica
  importa_raccolta.py     ← dal foglio (o da raccolta.json) alla cartella raccolta/
  correggi.py             ← voti, report, coppie sospette
verifiche/<MATERIA>/<verifica>/
  domande.json  chiave.json  studenti.csv  codici.csv  bigliettini.html
```

> ⚠️ `verifiche/` contiene le soluzioni: il repository deve essere **privato**.
> GitHub Pages su un repo privato richiede GitHub Pro, che è gratuito per i docenti con GitHub Education.
> Il sito resta pubblico, ma in `docs/` non ci sono né domande né soluzioni: le domande le manda lo script solo dopo l'accesso.

## Online: installazione (una volta sola)

1. Il foglio "Registro verifiche" (quello collegato all'Apps Script) contiene due schede:
   - `registro`: `id_foglio | verifica | materia | classe | creata | note`, cioè una riga per verifica;
   - `impostazioni`: `password | …`, la password del pannello docente.
2. In Apps Script incolla `apps-script/Codice.gs` ed esegui **`prepara`**. Autorizza l'accesso ai fogli: lo script deve poter aprire i fogli delle verifiche.
3. Distribuisci → App web:
   - *Esegui come*: Me;
   - *Chi ha accesso*: **Chiunque**.

   Metti l'URL `/exec` in `docs/config.js`.
4. Dopo ogni modifica di `Codice.gs` vai su Gestisci distribuzioni → matita → Versione: **Nuova versione**. L'URL non cambia.

## Online: una nuova verifica

La crea la skill **crea-verifica** di Claude, partendo dall'esercitazione fatta in classe. A mano i passaggi sono:

1. Scrivi `verifiche/<MATERIA>/<id>/domande.json` e `chiave.json`, poi lancia `python strumenti/valida.py verifiche/<MATERIA>/<id>`.
2. Prepara `studenti.csv` (`nome,classe`) e lancia `python strumenti/crea_codici.py verifiche/<MATERIA>/<id> verifiche/<MATERIA>/<id>/studenti.csv`.
3. Crea un Google Sheet nuovo. Lancia `python strumenti/prepara_foglio.py verifiche/<MATERIA>/<id>` e scrivi ogni scheda dalla cella A1. Le schede sono: impostazioni, codici, domande, sessioni, risposte, eventi.
4. Aggiungi una riga nel `registro` con l'ID del foglio. Lo script la vede entro 2 minuti.

Lo script non va toccato.

## Il giorno della verifica

1. Apri `docente.html`, metti la password, scegli la verifica e premi **Apri la verifica**.
   Puoi anche aprire direttamente `docente.html?v=<ID-foglio>`.
2. Gli studenti aprono la pagina principale e scrivono il codice. La pagina trova da sola, tra le verifiche **aperte**, quella in cui esiste quel codice.
   Si può dare anche il link con `?v=<ID-foglio>`.
3. Alla fine premi **Chiudi gli accessi**, poi **Scarica raccolta.json**.

## Correzione

```
python strumenti/importa_raccolta.py verifiche/<MATERIA>/<id> raccolta.json
python strumenti/correggi.py verifiche/<MATERIA>/<id>
```

Produce `risultati/risultati.csv` (da incollare nella griglia), `report.html` (coppie sospette, aperte raggruppate, eventi) e `aperte.csv`, dove metti i punti delle domande aperte prima di rilanciare.

## Laboratorio senza internet

```
pip install flask
python server.py verifiche/<MATERIA>/<id> --password segreta
```

Gli studenti aprono `http://IP-DEL-DOCENTE:5000`; il pannello è su `http://localhost:5000/docente`.

## Protezioni anti-copiatura

| Rischio | Cosa fa il sistema |
|---|---|
| Copiare dal vicino | Scenario, ordine, domande A/B, opzioni e colori diversi; dopo, segnalazione delle coppie con errori identici |
| Entrare al posto di un altro | Un codice funziona su un solo browser; da un altro serve «Sblocca» |
| Leggere tutte le domande dal codice della pagina | Il server manda **solo** lo scenario e le domande A/B dello studente |
| Consegnare dopo il tempo | Il server rifiuta i salvataggi dopo la scadenza (+60 s). Una consegna in ritardo vale con le risposte salvate prima della scadenza |
| Cambiare finestra o scheda, uscire dallo schermo intero, copiare | Registrato con la durata (non impedito) |
| Disattivare i controlli dalla console | Il pannello segnala «nessun segnale dai controlli» |
| **Telefono, secondo monitor, assistenti IA nel browser** | **Non rilevabili**: servono telefoni consegnati, giro tra i banchi, Safe Exam Browser |
