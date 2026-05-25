# Yahoo Finance Ticker Mapping

Dokumenterar hur symboler mappas till Yahoo Finance-tickers för börser som kräver suffix.

---

## Problem

Yahoo Finance använder olika tickerformat beroende på börs. För europeiska aktier
krävs ofta ett börs-suffix:

- **Euronext Paris**: `.PA` (t.ex. `OVH.PA`)
- **Frankfurt**: `.F` eller `.DE`
- **London**: `.L`
- etc.

Om man bara anger `OVH` utan suffix får Yahoo Finance ingen träff.

## Lösning

Modulen `data_fetcher.py` innehåller en mappningstabell `YAHOO_TICKER_MAP` som
översätter kortsymboler till Yahoo Finance-kompatibla tickers.

```python
YAHOO_TICKER_MAP: Dict[str, str] = {
    "OVH": "OVH.PA",  # Euronext Paris
}
```

När en symbol begärs kollar funktionen först i mappningen. Om symbolen finns där
används den mappade tickern för Yahoo Finance-anropet. Returnerad data behåller
ändå den ursprungliga symbolen (`OVH`) för konsistens med resten av systemet.

## Aktuella mappningar

| Symbol | Yahoo Ticker | Börs | Bolag |
|--------|-------------|------|-------|
| OVH | OVH.PA | Euronext Paris | OVH Groupe S.A. |

## Lägga till ny mappning

1. Identifiera rätt Yahoo Finance-ticker:
   - Sök på [Google Finance](https://www.google.com/finance) eller
     [Yahoo Finance](https://finance.yahoo.com)
   - Verifiera att data finns tillgänglig

2. Lägg till i `YAHOO_TICKER_MAP` i `src/data_fetcher.py`:
   ```python
   "SYMBOL": "SYMBOL.XX",  # Börsnamn
   ```

3. Lägg till test i `tests/test_data_fetcher.py`:
   ```python
   def test_yahoo_ticker_map_contains_new_symbol(self):
       from data_fetcher import YAHOO_TICKER_MAP
       assert "SYMBOL" in YAHOO_TICKER_MAP
       assert YAHOO_TICKER_MAP["SYMBOL"] == "SYMBOL.XX"
   ```

4. Uppdatera denna dokumentation.

## Varför inte Avanza?

Tidigare användes Avanza-webbskrapning som fallback för OVH. Detta ersattes
eftersom:

- **Yahoo Finance + yfinance är mer tillförlitligt** — ingen skrapning som kan gå sönder
- **Snabbare** — direkt API-anrop utan headless browser
- **Mindre komplext** — ingen regex-parsing av HTML
- **Standardiserat** — samma datakälla som alla andra aktier

Avanza-infrastrukturen finns kvar i koden som reserv om andra symboler
i framtiden behöver en fallback, men används inte aktivt just nu.

## Felsökning

### "No data returned for SYMBOL"
- Kontrollera att rätt ticker används (t.ex. `OVH.PA` inte bara `OVH`)
- Verifiera på Yahoo Finance att symbolen finns
- Kolla om börsen är öppen (helger/helgdagar ger tom data)

### Tickerformat för vanliga börser

| Börs | Suffix | Exempel |
|------|--------|---------|
| Euronext Paris | .PA | AIR.PA |
| Frankfurt/Xetra | .DE | SAP.DE |
| London | .L | BP.L |
| Tokyo | .T | 7203.T |
| Hong Kong | .HK | 0700.HK |

---

*Senast uppdaterad: 2026-05-25*
