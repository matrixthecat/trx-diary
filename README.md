# TRX Training Tracker

Mini web app personale per:
- registrare quando ti alleni (data precompilata automaticamente)
- segnare serie e ripetizioni per esercizio
- salvare peso e altezza su base settimanale
- modificare ed eliminare record direttamente dalle tabelle
- vedere una dashboard semplice dei progressi
- gestire una Wiki per ogni esercizio (descrizione, commento personale, foto, video link, video locali)
- avviare l'allenamento di oggi con timer, playlist video e check completamento

## Sicurezza (PIN)
- Accesso protetto da PIN locale.
- PIN iniziale: `1234` (oppure valore di `TRX_APP_PIN` al primo avvio).
- Puoi cambiare PIN dalla sezione `Sicurezza` dentro la dashboard.

## Stack
- Python + Flask
- SQLite (`training.db` locale)
- HTML/CSS/JS (Chart.js per grafici)

## Wiki esercizi
- Pagina `Wiki Esercizi` con scheda dedicata per ogni esercizio della routine.
- Media supportati:
   - foto (max 4 per esercizio)
   - link video esterni
   - video locali caricati e salvati nella cartella `video_esplicativi`
- Da scheda esercizio puoi aggiungere, modificare, sostituire o eliminare media.

## Avvia allenamento di oggi
- Pagina `Avvia Allenamento di Oggi` con:
   - timer (start/pausa/reset + preset secondi)
   - playlist che scorre automaticamente i video associati agli esercizi del giorno
   - checklist per segnare ogni esercizio come completato

## Avvio rapido
1. Crea ambiente virtuale (opzionale ma consigliato):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Installa dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
3. Avvia l'app:
   ```bash
   python3 app.py
   ```
4. Apri il browser su:
   ```
   http://127.0.0.1:5001
   ```

## Docker

L'app puo essere avviata in un container con dati persistenti in un volume Docker:

```bash
TRX_SECRET_KEY="una-chiave-lunga-e-casuale" TRX_APP_PIN="1234" docker compose up --build -d
```

Apri poi `http://127.0.0.1:5001`. Il database, le foto e i video caricati
vengono salvati nel volume `trx-data`, quindi restano disponibili dopo il
riavvio o la ricostruzione del container. Per rimuovere anche i dati:

```bash
docker compose down --volumes
```

## Struttura
- `app.py`: server Flask, routes, API dashboard
- `schema.sql`: schema SQLite
- `templates/`: pagine HTML
- `static/`: CSS e JavaScript
- `TRX_DATA_DIR` (opzionale): directory in cui salvare database e media; Docker la imposta su `/data`.

## Note
- Il database viene creato automaticamente al primo avvio.
- `week_start` e univoco: se salvi due volte la stessa settimana, i valori vengono aggiornati.
- I video locali vengono serviti da `video_esplicativi/`.
