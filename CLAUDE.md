# Verifiche online (IIS Galvani, prof. Fabio Malizia)

Istruzioni complete: `LEGGIMI.md`. In breve:

- Sito: GitHub Pages dalla **radice** del repository. La pagina studenti è `index.html`, che porta a `docs/`. Il pannello docente è `docs/docente.html?v=<ID-foglio>`.
- Server: un solo Apps Script (`apps-script/Codice.gs`). Lo pubblica il workflow `.github/workflows/apps-script.yml` a ogni push su `apps-script/`.
- Una verifica = cartella `verifiche/<MATERIA>/<id>/` + un Google Sheet registrato nel foglio "Registro verifiche" e in `verifiche.config.json`.
- Strumenti in `strumenti/`: `valida.py`, `crea_codici.py`, `prepara_foglio.py`, `importa_raccolta.py`, `correggi.py`.

Regole:

- **Il repository è pubblico.** Non fare commit di `verifiche/`, perché contiene le soluzioni. I sorgenti delle verifiche stanno come zip nella cartella Drive della materia.
- Non fare mai commit di `raccolta/`, `risultati/` o `raccolta.json`: sono dati degli studenti.
- Verifiche: 30 punti, voto = punti ÷ 3, 4 scenari, coppie A/B, testi brevi.
