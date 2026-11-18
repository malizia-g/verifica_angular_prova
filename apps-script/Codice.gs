/**
 * SERVER UNICO delle verifiche online (Apps Script collegato al foglio "Registro verifiche").
 *
 * - Il foglio collegato contiene la scheda "registro" (una riga per verifica) e "impostazioni" (password docente).
 * - Ogni verifica è un Google Sheet separato, creato dalla skill crea-verifica, con le schede:
 *     impostazioni | codici | domande | sessioni | risposte | eventi
 * - Lo script apre SOLO i fogli elencati nel registro.
 * - Non contiene e non riceve mai la chiave di correzione: si corregge dopo, con strumenti/correggi.py.
 *
 * Installazione (una volta sola): incolla questo file, esegui "prepara", poi
 * Distribuisci → App web → Esegui come: Me · Chi ha accesso: Chiunque.
 * Dopo ogni modifica del codice: Gestisci distribuzioni → matita → Versione: Nuova versione.
 */

const TOLLERANZA_S = 60;      // secondi concessi dopo la scadenza (rete lenta)
const SCHEDE_REGISTRO = {
  registro:     ["id_foglio", "verifica", "materia", "classe", "creata", "note"],
  impostazioni: ["chiave", "valore"]
};
const SCHEDE_VERIFICA = {
  impostazioni: ["chiave", "valore"],
  codici:       ["codice", "nome", "classe", "scenario", "postazione"],
  domande:      ["json"],
  sessioni:     ["codice", "token", "dispositivo", "inizio", "scadenza", "consegnata", "ora_consegna", "accessi", "eventi", "ultimo_salvataggio", "sbloccato", "browser"],
  risposte:     ["codice", "t", "stato", "automatica", "fuori_tempo", "versione", "risposte", "tempi"],
  eventi:       ["t", "ora", "codice", "tipo", "durata", "dettaglio", "dispositivo"]
};

/* ---------- da eseguire dall'editor ---------- */
function prepara() {
  const ss = SpreadsheetApp.getActive();
  Object.keys(SCHEDE_REGISTRO).forEach(function (n) { creaScheda(ss, n, SCHEDE_REGISTRO[n]); });
  ss.getSheetByName("registro").getRange("A:A").setNumberFormat("@");
  if (!trovaRiga(ss.getSheetByName("impostazioni"), "password", true)) ss.getSheetByName("impostazioni").appendRow(["password", "cambiami"]);
  // apre ogni foglio registrato: così Google chiede subito l'autorizzazione a leggerli
  registro().forEach(function (r) { SpreadsheetApp.openById(r.id_foglio).getName(); });
  CacheService.getScriptCache().removeAll(["registro", "aperte"]);
}

/* ---------- ingresso web ---------- */
function doGet() { return json({ ok: true, servizio: "verifiche" }); }

function doPost(e) {
  let d = {};
  try { d = JSON.parse((e && e.postData && e.postData.contents) || "{}"); } catch (x) {}
  let r;
  try {
    const f = AZIONI[d.azione];
    r = f ? f(d) : errore(400, "Azione sconosciuta");
  } catch (x) {
    r = errore(500, (x && x.message) || String(x));
  }
  return json(r);
}

const AZIONI = {
  /* --- studenti --- */
  accesso: function (d) {
    const cod = String(d.codice || "").trim().toUpperCase();
    let candidati;
    if (d.v) {
      if (!registrata(d.v)) return errore(404, "Verifica non trovata: controlla il link.");
      candidati = [d.v];
    } else {
      candidati = aperte();
      if (!candidati.length) return errore(403, "Nessuna verifica è aperta in questo momento. Aspetta il via del professore.");
    }
    let V = null, st = null;
    for (let i = 0; i < candidati.length && !st; i++) {
      const ss = apri(candidati[i]);
      if (!aperta(ss)) continue;
      st = leggi(ss, "codici", cod);
      if (st) V = { id: candidati[i], ss: ss };
    }
    if (!st) {
      if (d.v && !aperta(apri(d.v))) return errore(403, "La verifica non è ancora aperta. Aspetta il via del professore.");
      return errore(403, "Codice non valido. Controlla il bigliettino o chiama il professore.");
    }
    return conBlocco(function () {
      const ss = V.ss, ora = adesso();
      let s = leggi(ss, "sessioni", cod);
      if (s && vero(s.consegnata)) return errore(403, "Questa verifica è già stata consegnata.");
      if (s && !vero(s.sbloccato) && s.dispositivo && s.dispositivo !== d.dispositivo) {
        aggiungiEvento(ss, cod, "accesso-bloccato", "", "codice già usato su un altro dispositivo", d.dispositivo);
        return errore(403, "Codice già in uso su un altro computer. Chiama il professore.");
      }
      if (!s) s = { codice: cod, inizio: ora, scadenza: ora + durata(ss) * 60, consegnata: false, accessi: 0, eventi: 0 };
      const vecchio = s.token;
      s.token = Utilities.getUuid().replace(/-/g, "");
      s.dispositivo = d.dispositivo || "";
      s.sbloccato = false;
      s.accessi = Number(s.accessi || 0) + 1;
      s.browser = String(d.ua || "").slice(0, 200);
      scrivi(ss, "sessioni", s);
      const cache = CacheService.getScriptCache();
      if (vecchio) cache.remove("tok-" + vecchio);
      cache.put("tok-" + s.token, V.id + "|" + cod, 21600);
      const salv = leggi(ss, "risposte", cod);
      return {
        v: V.id, token: s.token, nome: st.nome, classe: st.classe, scenario: String(st.scenario || ""), seme: cod,
        scadenza: Number(s.scadenza), ora_server: ora,
        risposte: salv ? jsonDa(salv.risposte, {}) : {}, rientro: s.accessi > 1
      };
    });
  },

  /* solo la versione dello studente: il suo scenario e una domanda per ogni coppia A/B */
  domande: function (d) {
    const S = sessione(d), st = leggi(S.ss, "codici", S.codice);
    return personale(domandeDi(S.ss, S.v), S.codice, st && st.scenario);
  },

  salva: function (d) {
    const S = sessione(d);
    return conBlocco(function () {
      const s2 = leggi(S.ss, "sessioni", S.codice), ora = adesso();
      if (vero(s2.consegnata)) return errore(409, "Verifica già consegnata.");
      if (ora > Number(s2.scadenza) + TOLLERANZA_S) return errore(409, "Tempo scaduto: valgono le risposte salvate fino alla scadenza.");
      scrivi(S.ss, "risposte", { codice: S.codice, t: ora, stato: "salvataggio", automatica: "", fuori_tempo: "", versione: d.versione || {}, risposte: d.risposte || {}, tempi: d.tempi || {} });
      s2.ultimo_salvataggio = ora;
      scrivi(S.ss, "sessioni", s2);
      return { ok: true, scadenza: Number(s2.scadenza), ora_server: ora };
    });
  },

  /* segnale periodico della pagina: se sparisce mentre arrivano salvataggi, i controlli sono stati disattivati */
  battito: function (d) {
    const S = sessione(d);
    CacheService.getScriptCache().put("bat-" + S.v + "-" + S.codice, String(adesso()), 21600);
    return { ok: true };
  },

  evento: function (d) {
    const S = sessione(d);
    return conBlocco(function () {
      aggiungiEvento(S.ss, S.codice, String(d.tipo || "").slice(0, 40), d.durata, String(d.dettaglio || "").slice(0, 200), d.dispositivo);
      const s2 = leggi(S.ss, "sessioni", S.codice);
      s2.eventi = Number(s2.eventi || 0) + 1;
      scrivi(S.ss, "sessioni", s2);
      return { ok: true };
    });
  },

  consegna: function (d) {
    const S = sessione(d);
    return conBlocco(function () {
      const s2 = leggi(S.ss, "sessioni", S.codice), ora = adesso();
      if (vero(s2.consegnata)) return { ok: true, gia: true };
      const tardi = ora > Number(s2.scadenza) + TOLLERANZA_S;
      let rec = { codice: S.codice, t: ora, stato: "consegnata", automatica: !!d.automatica, fuori_tempo: "", versione: d.versione || {}, risposte: d.risposte || {}, tempi: d.tempi || {} };
      if (tardi) {   // fuori tempo: valgono solo le risposte salvate prima della scadenza
        const salv = leggi(S.ss, "risposte", S.codice) || {};
        rec.versione = jsonDa(salv.versione, rec.versione); rec.risposte = jsonDa(salv.risposte, {}); rec.tempi = jsonDa(salv.tempi, {});
        rec.automatica = true; rec.fuori_tempo = "SI";
        aggiungiEvento(S.ss, S.codice, "consegna-fuori-tempo", Math.round(ora - Number(s2.scadenza)), "risposte prese dall'ultimo salvataggio", d.dispositivo);
      }
      scrivi(S.ss, "risposte", rec);
      s2.consegnata = true; s2.ora_consegna = ora;
      scrivi(S.ss, "sessioni", s2);
      return { ok: true, fuori_tempo: tardi };
    });
  },

  /* --- docente (password nella scheda impostazioni del registro) --- */
  elenco: function (d) {
    controllaPassword(d);
    return {
      verifiche: registro().map(function (r) {
        let ap = false, tit = r.verifica;
        try { const ss = apri(r.id_foglio); ap = aperta(ss); } catch (x) { tit += " (foglio non raggiungibile)"; }
        return { v: r.id_foglio, verifica: tit, materia: r.materia, classe: r.classe, aperta: ap };
      })
    };
  },

  stato: function (d) {
    controllaPassword(d);
    const ss = apriRegistrata(d.v), codici = tutte(ss, "codici"), sess = {}, perDisp = {};
    tutte(ss, "sessioni").forEach(function (s) {
      sess[s.codice] = s;
      if (s.dispositivo) (perDisp[s.dispositivo] = perDisp[s.dispositivo] || []).push(s.codice);
    });
    const bat = CacheService.getScriptCache().getAll(codici.map(function (c) { return "bat-" + d.v + "-" + c.codice; }));
    const ora = adesso();
    const righe = codici.map(function (st) {
      const s = sess[st.codice] || {}, avvisi = [];
      const stessi = (perDisp[s.dispositivo] || []).filter(function (c) { return c !== st.codice; });
      if (s.dispositivo && stessi.length) avvisi.push("stesso computer di " + stessi.join(", "));
      if (Number(s.accessi) > 1) avvisi.push(s.accessi + " accessi");
      const inCorso = s.codice && !vero(s.consegnata);
      const b = Number(bat["bat-" + d.v + "-" + st.codice] || 0);
      if (inCorso && Number(s.ultimo_salvataggio) && (!b ? ora - Number(s.inizio) > 60 : Number(s.ultimo_salvataggio) - b > 90))
        avvisi.push("nessun segnale dai controlli (disattivati?)");
      if (inCorso && ora > Number(s.scadenza) + TOLLERANZA_S) avvisi.push("tempo scaduto, non ha consegnato");
      return {
        codice: st.codice, nome: st.nome, classe: st.classe, scenario: String(st.scenario || ""),
        ip: s.browser ? breveBrowser(s.browser) : "", postazione: st.postazione || "",
        stato: vero(s.consegnata) ? "consegnata" : (s.codice ? "in corso" : "non entrato"),
        eventi: Number(s.eventi || 0), ultimo: s.ultimo_salvataggio || null, scadenza: s.scadenza || null, avvisi: avvisi
      };
    });
    const D = domandeDi(ss, d.v);
    return { titolo: D.titolo || "", ora: ora, aperta: aperta(ss), righe: righe };
  },

  apri: function (d) {
    controllaPassword(d);
    const ss = apriRegistrata(d.v);
    impostazione(ss, "aperta", d.aperta ? "SI" : "NO");
    CacheService.getScriptCache().remove("aperte");
    return { ok: true };
  },

  sblocca: function (d) {
    controllaPassword(d);
    const ss = apriRegistrata(d.v);
    return conBlocco(function () {
      const cod = String(d.codice || "").toUpperCase(), s = leggi(ss, "sessioni", cod);
      if (s) { s.sbloccato = true; scrivi(ss, "sessioni", s); }
      aggiungiEvento(ss, cod, "sbloccato-dal-docente", "", "", "");
      return { ok: true };
    });
  },

  tempo: function (d) {
    controllaPassword(d);
    const ss = apriRegistrata(d.v);
    return conBlocco(function () {
      const cod = String(d.codice || "").toUpperCase(), s = leggi(ss, "sessioni", cod), min = Number(d.minuti || 5);
      if (s) { s.scadenza = Math.max(Number(s.scadenza), adesso()) + min * 60; scrivi(ss, "sessioni", s); }
      aggiungiEvento(ss, cod, "tempo-aggiunto", min, "", "");
      return { ok: true };
    });
  },

  /* tutto quello che serve a correggi.py, in un solo file */
  esporta: function (d) {
    controllaPassword(d);
    const ss = apriRegistrata(d.v);
    return {
      v: d.v, titolo: domandeDi(ss, d.v).titolo || "", esportato: adesso(),
      codici: tutte(ss, "codici"),
      sessioni: tutte(ss, "sessioni").map(function (s) { delete s.token; return s; }),
      risposte: tutte(ss, "risposte").map(function (r) {
        r.versione = jsonDa(r.versione, {}); r.risposte = jsonDa(r.risposte, {}); r.tempi = jsonDa(r.tempi, {}); return r;
      }),
      eventi: tutte(ss, "eventi").map(function (e) { delete e.ora; return e; })
    };
  }
};

/* ---------- registro e fogli delle verifiche ---------- */
function registro() {
  const cache = CacheService.getScriptCache(), c = cache.get("registro");
  if (c) return JSON.parse(c);
  const sh = SpreadsheetApp.getActive().getSheetByName("registro");
  const r = sh ? righe(sh).filter(function (x) { return String(x.id_foglio).trim(); }) : [];
  r.forEach(function (x) { x.id_foglio = String(x.id_foglio).trim(); });
  cache.put("registro", JSON.stringify(r), 120);
  return r;
}
function registrata(v) { return registro().some(function (r) { return r.id_foglio === String(v); }); }

const APERTI = {};   // fogli già aperti in questa esecuzione
function apri(v) { return APERTI[v] || (APERTI[v] = SpreadsheetApp.openById(v)); }
function apriRegistrata(v) {
  if (!v || !registrata(v)) throw new Error("Verifica non trovata nel registro.");
  return apri(v);
}
function aperta(ss) { return /^SI$/i.test(String(impostazione(ss, "aperta"))); }

function aperte() {
  const cache = CacheService.getScriptCache(), c = cache.get("aperte");
  if (c) return JSON.parse(c);
  const ids = registro().filter(function (r) { try { return aperta(apri(r.id_foglio)); } catch (x) { return false; } })
                        .map(function (r) { return r.id_foglio; });
  cache.put("aperte", JSON.stringify(ids), 300);
  return ids;
}

function domandeDi(ss, v) {
  const cache = CacheService.getScriptCache(), k = "dom-" + v, c = cache.get(k);
  if (c) return JSON.parse(c);
  const sh = ss.getSheetByName("domande");
  if (!sh || sh.getLastRow() < 2) throw new Error("Il foglio della verifica non ha la scheda domande.");
  const testo = sh.getRange(2, 1, sh.getLastRow() - 1, 1).getValues().map(function (r) { return String(r[0]); }).join("");
  const D = JSON.parse(testo);
  if (testo.length < 95000) cache.put(k, testo, 600);
  return D;
}
function durata(ss) { return Number(impostazione(ss, "durata_min") || domandeDi(ss, ss.getId()).durata_min || 60); }

function personale(D, cod, scenario) {
  const P = JSON.parse(JSON.stringify(D)), n = (D.scenari || []).length;
  if (n) {
    let i = Number(scenario);
    i = i >= 1 ? (i - 1) % n : numero(cod + "|scenario") % n;
    P.scenari = [D.scenari[i]];
    P.scenario_numero = i + 1;
  }
  (P.esercizi || []).forEach(function (e) {
    if (e.coppie) e.coppie = e.coppie.map(function (c, k) { return [c[numero(cod + "|" + e.id + "|" + k) % c.length]]; });
  });
  return P;
}
function numero(s) {
  const b = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, s);
  return (((b[0] & 255) << 16) | ((b[1] & 255) << 8) | (b[2] & 255)) >>> 0;
}

function sessione(d) {
  const tok = String(d.token || "");
  if (!tok) throw new Error("Sessione scaduta: rientra con il tuo codice.");
  const c = CacheService.getScriptCache().get("tok-" + tok);
  let v = c ? c.split("|")[0] : String(d.v || ""), cod = c ? c.split("|")[1] : "";
  const ss = apriRegistrata(v);
  let s = cod ? leggi(ss, "sessioni", cod) : null;
  if (!s || s.token !== tok) s = tutte(ss, "sessioni").filter(function (x) { return x.token === tok; })[0];
  if (!s) throw new Error("Sessione scaduta: rientra con il tuo codice.");
  return { v: v, ss: ss, codice: s.codice };
}

function controllaPassword(d) {
  if (String(d.password || "") !== String(impostazione(SpreadsheetApp.getActive(), "password")))
    throw new Error("Password del docente sbagliata.");
}

/* ---------- aiuti ---------- */
function json(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function errore(status, testo) { return { errore: testo, status: status }; }
function adesso() { return Date.now() / 1000; }
function vero(v) { return v === true || /^(true|vero|si)$/i.test(String(v)); }
function jsonDa(s, def) { if (s && typeof s === "object") return s; try { return s ? JSON.parse(s) : def; } catch (x) { return def; } }
function breveBrowser(ua) { const m = String(ua).match(/(Edg|Chrome|Firefox|Safari)\/[\d]+/); return m ? m[0] : "browser"; }

function creaScheda(ss, n, intest) {
  const sh = ss.getSheetByName(n) || ss.insertSheet(n);
  if (sh.getLastRow() === 0) { sh.appendRow(intest); sh.setFrozenRows(1); }
  return sh;
}

function conBlocco(f) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return errore(503, "Server occupato, riprovo.");
  try { return f(); } finally { lock.releaseLock(); }
}

function impostazione(ss, chiave, valore) {
  const sh = ss.getSheetByName("impostazioni"), r = trovaRiga(sh, chiave, true);
  if (valore === undefined) return r ? sh.getRange(r, 2).getValue() : "";
  if (r) sh.getRange(r, 2).setValue(valore); else sh.appendRow([chiave, valore]);
}

function intestazioni(sh) { return sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]; }

function trovaRiga(sh, chiave, esatta) {
  const n = sh.getLastRow(); if (n < 2) return 0;
  const col = sh.getRange(2, 1, n - 1, 1).getValues(), k = esatta ? String(chiave) : String(chiave).trim().toUpperCase();
  for (let i = 0; i < col.length; i++) {
    const v = esatta ? String(col[i][0]) : String(col[i][0]).trim().toUpperCase();
    if (v === k) return i + 2;
  }
  return 0;
}

function righe(sh) {
  if (sh.getLastRow() < 2) return [];
  const v = sh.getDataRange().getValues(), h = v.shift();
  return v.filter(function (r) { return String(r[0]).trim() !== ""; }).map(function (r) {
    const o = {}; h.forEach(function (k, j) { o[k] = r[j]; }); return o;
  });
}

function leggi(ss, nome, codice) {
  const sh = ss.getSheetByName(nome), r = trovaRiga(sh, codice); if (!r) return null;
  const h = intestazioni(sh), v = sh.getRange(r, 1, 1, h.length).getValues()[0], o = {};
  h.forEach(function (k, j) { o[k] = v[j]; });
  o.codice = String(o.codice).trim().toUpperCase();
  return o;
}

function tutte(ss, nome) {
  return righe(ss.getSheetByName(nome)).map(function (o) {
    o.codice = nome === "eventi" ? String(o.codice) : String(o.codice).trim().toUpperCase(); return o;
  });
}

function scrivi(ss, nome, o) {
  const sh = ss.getSheetByName(nome), h = intestazioni(sh);
  const v = h.map(function (k) {
    const x = o[k];
    if (x === undefined || x === null) return "";
    return typeof x === "object" ? JSON.stringify(x) : x;
  });
  const r = trovaRiga(sh, o.codice);
  if (r) sh.getRange(r, 1, 1, v.length).setValues([v]); else sh.appendRow(v);
}

function aggiungiEvento(ss, codice, tipo, durata, dettaglio, dispositivo) {
  ss.getSheetByName("eventi").appendRow([adesso(), new Date(), codice, tipo, durata === undefined || durata === null ? "" : durata, dettaglio || "", dispositivo || ""]);
}
