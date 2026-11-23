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
4. Dopo ogni modifica di `Codice.gs` la nuova versione la pubblica GitHub da solo (vedi *Aggiornamento automatico dello script*). A mano: Gestisci distribuzioni → matita → Versione: **Nuova versione**. L'URL non cambia.

## Aggiornamento automatico dello script

Il workflow `.github/workflows/apps-script.yml` parte a ogni push che modifica `apps-script/`
(oppure da Actions → *Pubblica Apps Script* → **Run workflow**). Con `clasp`:

1. scarica dal progetto attuale solo `appsscript.json` (le impostazioni dell'app web restano quelle di Google);
2. carica `apps-script/*.gs` (`clasp push --force`);
3. pubblica una nuova versione sulla **stessa** distribuzione (`clasp deploy --deploymentId …`): l'URL `/exec` non cambia.

Configurazione, una volta sola (Settings → Secrets and variables → Actions):

| Nome | Tipo | Valore |
|---|---|---|
| `CLASPRC_JSON` | secret | contenuto di `~/.clasprc.json` dell'account **proprietario dello script** (account della scuola) |
| `SCRIPT_ID` | variable | Apps Script → Impostazioni progetto → ID script (progetto aperto da *Registro verifiche → Estensioni → Apps Script*) |
| `DEPLOYMENT_ID` | variable | la parte dell'URL dell'app web tra `/s/` e `/exec` |

Prerequisito: API Google Apps Script attiva in https://script.google.com/home/usersettings.

Per ottenere `~/.clasprc.json` in un Codespace:

- `clasp login --no-localhost` **non funziona più** (Google ha disattivato quel metodo).
- `clasp login` nel Codespace si interrompe con *Error retrieving access token: null*, perché il Codespace "tocca" da solo la porta locale.
- Funziona `clasp login` dal proprio PC, oppure uno script che fa l'accesso OAuth a mano (redirect su `http://localhost:8888`, si incolla l'indirizzo finale) e scrive `~/.clasprc.json`.

Controlla l'account con `clasp login --status`.

Errori tipici nel log del workflow:

- *Could not find script* → `SCRIPT_ID` sbagliato oppure credenziali di un altro account;
- *User has not enabled the Apps Script API* → prerequisito mancante.

## Online: una nuova verifica

La crea la skill **crea-verifica** di Claude, partendo dall'esercitazione fatta in classe. A mano i passaggi sono:

1. Scrivi `verifiche/<MATERIA>/<id>/domande.json` e `chiave.json`, poi lancia `python strumenti/valida.py verifiche/<MATERIA>/<id>`.
2. Prepara `studenti.csv` (`nome,classe`) e lancia `python strumenti/crea_codici.py verifiche/<MATERIA>/<id> verifiche/<MATERIA>/<id>/studenti.csv`.
3. Crea un Google Sheet nuovo. Lancia `python strumenti/prepara_foglio.py verifiche/<MATERIA>/<id>` e scrivi ogni scheda dalla cella A1. Le schede sono: impostazioni, codici, domande, sessioni, risposte, eventi.
4. Aggiungi una riga nel `registro` con l'ID del foglio. Lo script la vede entro 2 minuti.
5. Aggiungi la verifica in `verifiche.config.json`, sotto `verifiche`:
   `"<MATERIA>/<id>": {"foglio": "<ID-foglio>", "classe": "4E", "titolo": "05.3.5 Git branch…", "creata": "AAAA-MM-GG"}`.
   Al push, il workflow *Aggiorna wiki* riscrive la pagina wiki **Registro verifiche**.

Lo script non va toccato.

## Registro nella wiki

La pagina wiki *Registro verifiche* elenca tutte le verifiche divise per materia e anno (TPSI - 3, TPSI - 4, …).
Per ognuna dà il foglio Google (risposte e correzione), il pannello docente e la pagina studenti con `?v=<ID-foglio>`.

- La genera `strumenti/aggiorna_wiki.py` da `verifiche.config.json`. Non va modificata a mano.
- Il workflow `.github/workflows/wiki.yml` la aggiorna a ogni push che cambia il config. A mano: Actions → *Aggiorna wiki* → **Run workflow**.
- Prima volta: la wiki deve già esistere (scheda Wiki → *Create the first page* → salva).

> La wiki di un repository pubblico è pubblica. I fogli Google restano protetti dai loro permessi e il pannello docente dalla password.

## Il giorno della verifica

1. Apri `docs/docente.html` (https://malizia-g.github.io/verifica_angular_prova/docs/docente.html), metti la password, scegli la verifica e premi **Apri la verifica**.
   Puoi anche aprire direttamente `docs/docente.html?v=<ID-foglio>`: il sito è pubblicato dalla radice del repository, quindi nel percorso serve `docs/`.
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
