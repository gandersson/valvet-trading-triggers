# Avanza Fallback — Dokumentation (DEPRECATED)

> ⚠️ **Denna fallback är för närvarande INAKTIV.**
> 
> OVH hämtas nu direkt från Yahoo Finance via ticker-mappning (`OVH` → `OVH.PA`).
> Se [yahoo-ticker-mapping.md](yahoo-ticker-mapping.md) för aktuell information.
> 
> Avanza-infrastrukturen behålls i koden som reserv för framtida behov.

---

## Historik

Tidigare användes Avanza-webbskrapning som fallback för symboler som inte hade
data på Yahoo Finance. Den enda symbolen som behövde detta var **OVH** (OVH
Groupe, noterad på Euronext Paris).

Problemet visade sig vara att Yahoo Finance kräver börs-suffixet `.PA` för
Euronext Paris-aktier, inte att data saknades helt.

## Lösning

Se [yahoo-ticker-mapping.md](yahoo-ticker-mapping.md) för hur ticker-mappning
nu hanterar detta via `YAHOO_TICKER_MAP` i `src/data_fetcher.py`.

## Kvarvarande infrastruktur

Följande komponenter finns kvar i `data_fetcher.py` men används inte aktivt:

- `AVANZA_FALLBACK_SYMBOLS` — nu tom `set()`
- `AVANZA_URLS` — nu tom `dict`
- `fetch_avanza_data()` — fungerar om konfigurerad
- `_parse_avanza_html()` — HTML-parser för Avanza
- `_run_agent_browser()` — browser-automation wrapper

## Återaktivering

Om en symbol i framtiden behöver Avanza-fallback:

1. Lägg till symbolen i `AVANZA_FALLBACK_SYMBOLS`
2. Lägg till URL i `AVANZA_URLS`
3. Uppdatera tester i `tests/test_data_fetcher.py`
4. Uppdatera dokumentationen

---

## Originaldokumentation

För fullständig teknisk dokumentation av Avanza-parsern (HTML-strukturer,
regex-mönster, etc.), se historiska versioner av denna fil i git-loggen.

*Senast uppdaterad: 2026-05-25*
