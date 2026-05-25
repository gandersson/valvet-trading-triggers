# Avanza Fallback — Dokumentation

Dokumenterar hur fallback-logiken fungerar för att hämta aktiedata från Avanza när Yahoo Finance saknar data eller är otillgänglig.

---

## Varför Avanza Fallback?

Yahoo Finance har begränsat stöd för vissa europeiska aktier, särskilt mindre bolag noterade på Euronext Paris. OVH Groupe (OVH) är ett exempel — Yahoo Finance returnerar ofta ofullständig eller saknad data.

Avanza erbjuder däremot täckning för OVH och många andra europeiska aktier med realtidskurser.

---

## Arkitektur

```
┌─────────────────────────────────────────────────────────────┐
│                    fetch_stock_data_with_fallback              │
│                          (data_fetcher.py)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
    ┌──────▼──────┐         ┌─────▼──────┐
    │   Yahoo     │         │   Avanza   │
    │  Finance    │         │  Scraper   │
    └──────┬──────┘         └─────┬──────┘
           │                      │
           │   Fallback vid fel   │
           └──────────────────────►│
                                  │
                           ┌──────▼──────┐
                           │ agent-browser │
                           │ (headless)   │
                           └─────────────┘
```

---

## Implementation

### Huvudmodul: `src/data_fetcher.py`

**`fetch_stock_data_with_fallback(symbol: str) -> Dict`**

Huvudfunktionen som koordinerar datahämtning:

1. Kollar om symbolen finns i `AVANZA_FALLBACK_SYMBOLS`
2. Om inte: använd Yahoo Finance direkt
3. Om ja: försök Yahoo Finance först, fall tillbaka på Avanza vid fel

**`fetch_stock_data_yahoo(symbol: str) -> Dict`**

Omsluter den gamla `fetch_stock_data()` med retry-logik via `tenacity`.

**`fetch_avanza_data(symbol: str) -> Dict`**

Skrapar Avanza-sidan via headless browser:
1. Öppnar Avanza-URL med `agent-browser open`
2. Kör JavaScript för att hämta HTML: `document.documentElement.outerHTML`
3. Stänger browsern
4. Parsar HTML med regex för att extrahera prisdata

**`_parse_avanza_html(html: str, symbol: str) -> Dict`**

Extraherar följande fält från Avanza HTML:
- **Senast betalt** → `price`
- **Högst** → `high`
- **Lägst** → `low`
- **Förändring %** → `change_pct`
- **Öppningspris** → beräknas från `price / (1 + change_pct/100)`
- **Volym** → sätts till 0 (Avanza visar inte alltid volym på sidan)

---

## Konfiguration

### Fallback-symboler

```python
AVANZA_FALLBACK_SYMBOLS: set[str] = {"OVH"}
```

Lägg till nya symboler här om de behöver Avanza-fallback.

### Avanza URLs

```python
AVANZA_URLS: Dict[str, str] = {
    "OVH": "https://www.avanza.se/aktier/om-aktien.html/1326722/ovh-groupe-prom-eo-1",
}
```

Varje symbol behöver en motsvarande Avanza-URL. URL-formatet är:
- Bas: `https://www.avanza.se/aktier/om-aktien.html/`
- ID: Avanzas interna aktie-ID (t.ex. `1326722`)
- Slug: Aktiens namn i URL-vänligt format

**Så hittar du URL:en:**
1. Gå till Avanza och sök aktien
2. Kopiera URL:en från addressfältet
3. Lägg till i `AVANZA_URLS`

---

## Beroenden

### Python-paket
- `yfinance` — Yahoo Finance-data
- `tenacity` — retry-logik
- Standardbibliotek: `re`, `subprocess`, `logging`

### Systemberoenden
- `agent-browser` — headless browser automation CLI
  - Installera: `npm install -g agent-browser`
  - Verifiera: `agent-browser --version`

---

## Parser-detaljer

### Pris-extraktion

Avanza visar pris på svenska format:
```
Senast betalt
11,74 EUR
```

Parser hanterar:
- Komma som decimalseparator: `11,74` → `11.74`
- Tusentalsavgränsare: `1 234,56` → `1234.56`
- Valutakod: `11,74 EUR` → `11.74`

### Förändring

Format: `X,XX% (Y,YY)` eller bara `+X,XX%`
- `0,00% (0,00)` → `change_pct: 0.0`
- `+1,29%` → `change_pct: 1.29`
- `-2,89%` → `change_pct: -2.89`

### Högsta/Lägsta

Format: `Högst X,XX Lägst Y,YY`
- Extraheras med regex: `r"Högst\s+([\d\s,\.]+)\s+Lägst\s+([\d\s,\.]+)"`

---

## Begränsningar

| Begränsning | Förklaring | Workaround |
|-------------|-----------|------------|
| **Volym** | Avanza visar inte alltid volym på "Om aktien"-sidan | Sätts till 0; hämta från historik om nödvändigt |
| **Öppningspris** | Hämtas inte direkt, beräknas | `open = price / (1 + change_pct/100)` |
| **Browser overhead** | Varje anrop startar/stänger browser | Cache-resultat vid upprepade anrop |
| **Parsing skörhet** | Regex-baserad parsing kan bryta vid UI-ändringar | Använd snapshot-tester för att upptäcka ändringar |
| **Tidszoner** | Avanza visar CET/CEST-tider | Timestamps sparas i lokal tid |

---

## Felsökning

### "agent-browser not found"
```bash
npm install -g agent-browser
agent-browser install --with-deps
```

### "Empty or too short response"
- Avanza-sidan kan ha blockerats
- Testa manuellt: `agent-browser open https://www.avanza.se/aktier/om-aktien.html/1326722/ovh-groupe-prom-eo-1`
- Kolla att sidan laddar korrekt

### Felaktigt pris
- Avanza kan ha ändrat HTML-strukturen
- Inspektera HTML: `agent-browser snapshot > page.html`
- Uppdatera regex i `_parse_avanza_html()`

---

## Tester

14 tester i `tests/test_data_fetcher.py`:

| Test | Vad det testar |
|------|---------------|
| `test_fetch_stock_data_yahoo_success` | Yahoo Finance-path fungerar |
| `test_fetch_stock_data_yahoo_empty_data` | Hantering av tom data |
| `test_fetch_stock_data_with_fallback_for_non_fallback_symbol` | Icke-fallback-symboler använder Yahoo |
| `test_parse_avanza_price` | Svenskt prisformat |
| `test_parse_avanza_change` | Svenskt procentformat |
| `test_parse_avanza_html_basic` | HTML-parsing med nollförändring |
| `test_parse_avanza_html_with_change` | HTML-parsing med förändring |
| `test_avanza_fallback_symbol_configured` | OVH finns i fallback-listan |
| `test_avanza_url_configured` | OVH har URL |
| `test_fetch_avanza_unsupported_symbol` | Ogiltig symbol ger ValueError |
| `test_fetch_avanza_data_success` | Mockad browser-returnerar data |
| `test_fallback_chain_yahoo_fails` | Fallback aktiveras vid Yahoo-fel |
| `test_fallback_chain_yahoo_succeeds` | Yahoo används när det fungerar |
| `test_fetch_stock_data_compatibility` | API-kompatibilitet |

---

## Framtida förbättringar

- [ ] Cache:a Avanza-resultat i minnet för att minska browser-overhead
- [ ] Lägg till stöd för fler europeiska börser (Tyskland, Nederländerna)
- [ ] Implementera rate limiting för att inte överbelasta Avanza
- [ ] Lägg till selenium/playwright som alternativ till agent-browser
- [ ] Extrahera volym från Avanza historik-tabell

---

*Senast uppdaterad: 2026-05-25*
*Av: Marvin 🤖*
