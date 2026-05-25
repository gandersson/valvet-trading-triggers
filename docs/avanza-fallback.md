# Avanza Fallback

## Syfte
Avanza-fallback är nu en **aktiv del av resiliency-strategin** för utvalda europeiska aktier där Yahoo Finance har intermittent datakvalitet.

Systemet försöker alltid Yahoo Finance först (med rätt börssuffix via `YAHOO_TICKER_MAP`). Om Yahoo misslyckas för en symbol som är markerad som "fallback-värdig", hämtas data istället från Avanza via webbskrapning.

---

## Aktiva symboler (uppdat 2026-05-25)

| Symbol | Börssuffix | Avanza-grund |
|--------|-----------|-------------|
| **OVH** | `.PA` (Euronext Paris) | Molntjänster i Europa |
| **ASML** | `.AS` (Euronext Amsterdam) | Litografimaskiner |

## Symboler med Yahoo-mappning (ingen aktiv fallback)

Dessa aktier har börssuffix i `YAHOO_TICKER_MAP`, men Yahoo Finance används direkt utan fallback:

| Symbol | Börssuffix | Sektor |
|--------|-----------|--------|
| **SAP** | `.DE` (Xetra Frankfurt) | Enterprise-programvara |
| **ADYEN** | `.AS` (Euronext Amsterdam) | Betalningar/Fintech |
| **SIE** | `.DE` (Xetra Frankfurt) | Industri/konglomerat |

---

## Konfiguration

All konfiguration finns i `src/data_fetcher.py`:

- `YAHOO_TICKER_MAP` — intern symbol → Yahoo ticker med börssuffix
- `AVANZA_FALLBACK_SYMBOLS` — symboler som får Avanza-reserv vid Yahoo-fel
- `AVANZA_URLS` — direkta URL:er för varje fallback-symbol

Exempel:
```python
YAHOO_TICKER_MAP = {
    "OVH": "OVH.PA",       # Euronext Paris
    "ASML": "ASML.AS",     # Euronext Amsterdam
    "SAP": "SAP.DE",       # Xetra Frankfurt
    ...
}

AVANZA_FALLBACK_SYMBOLS = {"OVH", "ASML"}

AVANZA_URLS = {
    "OVH": "https://www.avanza.se/aktier/om-aktien.html/1326722/ovh-groupe-prom-eo-1",
    "ASML": "https://www.avanza.se/aktier/om-aktien.html/5320/asml-holding",
}
```

---

## Fallback-flöde

```
symbol i AVANZA_FALLBACK_SYMBOLS?
├─ NEJ → Yahoo only (med eventuell ticker-mappning)
└─ JA  → Yahoo first → Avanza vid misslyckande
              ↓                ↓
         [success]        [success]
              ↓                ↓
         return data       return data
              ↓                ↓
         source=yahoo    source=avanza
```

---

## Risker

- **HTML-förändringar**: Om Avanza ändrar sidstrukturen slutar parsern fungera. Bevakas via tester `test_parse_avanza_html_*`.
- **Data-inkonsekvens**: Avanza visar inte alltid volym; `volume = 0` används som placeholder. Öpris beräknas ibland bakåt från pris + förändring.
- **Körtid**: Browser-scraping är långsammare. Fallback bör begränsas till utvalda symboler.

---

## Utöka med nya EU-symboler

1. Verifiera Yahoo-ticker med börssuffix på [finance.yahoo.com](https://finance.yahoo.com/)
2. Hitta Avanza-URL via sökning på [avanza.se](https://www.avanza.se/)
3. Lägg till i `YAHOO_TICKER_MAP`, `AVANZA_URLS` (om fallback behövs)
4. Uppdatera `STOCKS` och `create_triggers` i `trigger_system_v1.py`
5. Lägg till test i `tests/test_data_fetcher.py` för mapping och/eller fallback
6. Kör full testsviten för regression

---

## Teknisk referens

- Parser: `_parse_avanza_html()` i `src/data_fetcher.py`
- Browser: `agent-browser` CLI (headless automation)
- Retry: `@retry_yfinance` (3 försök, exponentiell backoff) gäller endast Yahoo-sidan

*Senast uppdaterad: 2026-05-25*
