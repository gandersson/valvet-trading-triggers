# Known Issues and Limitations

Dokumenterar kända begränsningar och problem i trading-triggers.

---

## Datakällor

### Yahoo Finance

**Status:** ✅ Primär källa, fungerar bra

**Begränsningar:**
- Vissa europeiska aktier kräver börs-suffix (t.ex. `.PA` för Euronext Paris)
- Lösning: `YAHOO_TICKER_MAP` i `data_fetcher.py` hanterar mappningen
- Helg- och helgdagsdata kan vara ofullständig
- Rate limiting kan förekomma vid många anrop

### Avanza Fallback

**Status:** ⚠️ Inaktiv (infrastruktur finns kvar)

**Begränsningar:**
- Kräver `agent-browser` (headless browser)
- Skrapning är känslig för UI-ändringar på Avanzas webbplats
- Visar inte alltid volymdata
- Beräknat öppningspris från förändring kan avvika från verkligt värde
- Långsammare än direkta API-anrop p.g.a. browser-start

**Varför inaktiv:** OVH (den enda aktiva fallback-symbolen) fungerar nu
via Yahoo Finance med ticker-suffixet `.PA`. Avanza-fallbacken behålls
för framtida behov om en symbol inte har en Yahoo-kompatibel ticker.

---

## Symbolspecifika frågor

### OVH (OVH Groupe)

**Status:** ✅ Löst

**Historiskt problem:** Yahoo Finance hade ingen data för `OVH` (bär symbol).
**Lösning:** Mappad till `OVH.PA` i `YAHOO_TICKER_MAP`.
**Verifikation:** Data hämtas framgångsrikt via yfinance med `OVH.PA`.

---

## Testning

### Integrationstester med nätverksanrop

- Tester som anropar riktiga API:er (Yahoo Finance) kan vara långsamma
- Vissa tester mockar ut externa beroenden
- För fullständig integrationstestning, kör `python src/data_fetcher.py`

---

## Framtida förbättringar

### Datakällor
- [ ] Lägg till backup-källa om Yahoo Finance är nere (t.ex. Alpha Vantage)
- [ ] Implementera cachning av hämtade data för att minska API-anrop
- [ ] Lägg till stöd för realtidsdata via WebSocket

### Robusthet
- [ ] Lägg till health-check för datakällor innan de används
- [ ] Implementera graceful degradation vid temporära fel
- [ ] Lägg till datakvalitetskontroll (t.ex. pris inom rimligt intervall)

### Utökning
- [ ] Stöd för fler europeiska börser (London, Frankfurt, Amsterdam)
- [ ] Automatisk identifiering av rätt börs-suffix för nya symboler
- [ ] Stöd för valutaomräkning om data levereras i annan valuta

---

*Senast uppdaterad: 2026-05-25*
