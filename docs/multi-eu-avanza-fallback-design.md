# Design: Stöd för flera europeiska aktier med Avanza-fallback

## Bakgrund och nuläge

Nuvarande implementation i `src/data_fetcher.py`:

- `YAHOO_TICKER_MAP` används för börssuffix (idag i praktiken främst `OVH -> OVH.PA`)
- `AVANZA_FALLBACK_SYMBOLS` är tom
- `AVANZA_URLS` är tom
- `fetch_stock_data_with_fallback(symbol)` har redan fallbackflödet:
  - Yahoo direkt för symboler som inte ligger i fallback-set
  - Yahoo först och Avanza som reserv för fallback-symboler

Det betyder att infrastrukturen redan finns, men den är inte konfigurerad för flera europeiska aktier.

---

## Mål

Införa robust stöd för flera europeiska aktier där Yahoo är primär källa och Avanza fallback vid Yahoo-fel eller saknad data.

Målet är att utöka funktionalitet med minimal kodförändring och bibehållen kompatibilitet mot:

- `src/trigger_system_v1.py`
- `src/api_server.py`
- befintligt dataskema och returformat

---

## Icke-mål (för denna leverans)

- Ingen ny extern datakälla (Alpha Vantage, IEX, Polygon)
- Ingen valutaräkning/FX-normalisering
- Ingen större refaktor av `trigger_system_v1.py`
- Ingen ändring av DB-schema

---

## Föreslagen design

### 1) Konfigurationsmodell per symbol

Behåll `data_fetcher.py` som central plats men introducera tydligare symbolkonfiguration:

- `YAHOO_TICKER_MAP`: intern symbol -> Yahoo ticker med suffix
- `AVANZA_URLS`: intern symbol -> Avanza-URL
- `AVANZA_FALLBACK_SYMBOLS`: symboler som får Avanza-reserv

Designprincip:

- **Intern symbol förblir utan suffix** (exempel `ASML`) i resten av systemet
- Yahoo-mappning hanterar suffix internt (`ASML -> ASML.AS`)
- Avanza fallback styrs av intern symbol (`ASML`), inte Yahoo ticker

Detta minimerar påverkan på triggers, DB och rapportering.

### 2) Datakällestrategi

För varje symbol väljs en av två strategier:

1. **Yahoo-only**
   - Symbol finns i `YAHOO_TICKER_MAP` eller fungerar direkt
   - Ej med i `AVANZA_FALLBACK_SYMBOLS`
2. **Yahoo-then-Avanza**
   - Symbol finns i `AVANZA_FALLBACK_SYMBOLS`
   - Försök Yahoo först, fallback till Avanza vid fel

Vi använder endast strategi 2 för symboler där Yahoo historiskt är instabilt.

### 3) Utökning av europeiska symboler (fas 1)

Initial uppsättning (förslag):

- Frankrike: `OVH -> OVH.PA`
- Tyskland: `SAP -> SAP.DE`, `SIE -> SIE.DE`
- Nederländerna: `ASML -> ASML.AS`, `ADYEN -> ADYEN.AS`

Obs: faktisk lista fastställs innan implementation med verifierade Avanza-URL:er.

### 4) Felhantering och observability

Behåll existerande mönster:

- `@retry_yfinance` för Yahoo
- sammanfattande `RuntimeError` om båda källor fallerar
- `source` i returdata (`"yahoo"` eller `"avanza"`) för felsökning

Utökning i implementationen ska hålla loggnivåer tydliga:

- `info`: källa som lyckades
- `warning`: Yahoo misslyckades men fallback försöks
- `error`: båda källor misslyckades

---

## Påverkade filer vid implementation (plan)

- `src/data_fetcher.py`
  - fylla på symbolmappning, fallback-symboler och Avanza-URL:er
  - eventuellt mindre justering för tydligare validering
- `src/trigger_system_v1.py`
  - utöka `STOCKS` med beslutade EU-symboler
- `tests/test_data_fetcher.py`
  - nya tester för fler EU-symboler och fallbackscenarier
- `docs/avanza-fallback.md`
  - uppdatera från “deprecated/inaktiv” till aktiv fler-symbolsstrategi

---

## Risker och motåtgärder

1. **Avanza HTML förändras**
   - Risk: regex-parser slutar hitta pris
   - Motåtgärd: tester med representativa HTML-snippets + tydlig feltext

2. **Yahoo fungerar intermittent för vissa tickers**
   - Risk: flappande datakvalitet
   - Motåtgärd: fallback bara för utvalda symboler med historiska problem

3. **Inkonsekvens i volym/open mellan källor**
   - Risk: små skillnader i trigger-evaluering
   - Motåtgärd: dokumentera avvikelse; behåll samma normaliserade returformat

4. **Ökad körtid vid fler fallback-anrop**
   - Risk: långsammare daglig körning
   - Motåtgärd: begränsa fallback-symboler i första iteration

---

## Teststrategi för implementation

### Enhetstester

- Yahoo-mappning per ny EU-symbol (`symbol -> suffix`)
- Fallbackväg för symbol i `AVANZA_FALLBACK_SYMBOLS`:
  - Yahoo-fel simuleras
  - Avanza-svar returneras korrekt
- Felväg när både Yahoo och Avanza misslyckas

### Integration/smoke

- Kör `python src/trigger_system_v1.py` med minst en ny EU-symbol i `STOCKS`
- Verifiera att symbol kan processas end-to-end och sparas i DB

### Regression

- Befintliga symboler (NVDA, WMT, etc.) ska fortsätta gå via Yahoo utan beteendeförändring

---

## Definition of Done (innan implementation betraktas klar)

- [ ] Minst 5 europeiska symboler är definierade med verifierad Yahoo-mappning
- [ ] Avanza-URL finns för varje symbol som markerats för fallback
- [ ] `fetch_stock_data_with_fallback()` väljer källa enligt design (Yahoo-only vs Yahoo-then-Avanza)
- [ ] Nya tester finns för:
  - [ ] mappning av nya EU-symboler
  - [ ] fallback när Yahoo fallerar
  - [ ] fel när båda källor fallerar
- [ ] Befintliga tester relaterade till `data_fetcher` och triggerflöde passerar
- [ ] Minst ett manuellt smoke-test är kört genom systemets CLI-yta (`python src/trigger_system_v1.py`)
- [ ] Dokumentation uppdaterad (`docs/avanza-fallback.md` + denna designfil)
- [ ] Ingen ändring av DB-schema och inga nya dependencies i `requirements.txt`

---

## Beslutspunkter att bekräfta innan implementation

1. Exakt lista av första EU-symboler (5 st)
2. Vilka av dessa ska ha Avanza fallback från dag 1
3. Om vi vill lägga in dem direkt i `STOCKS` eller feature-flagga inför gradvis aktivering
