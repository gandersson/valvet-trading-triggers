# Signalstyrka — Designbeslut

Dokumenterar varför signalstyrka-algoritmen ser ut som den gör i `src/signal_generator.py`.

---

## Confidence Score = N1 × N2 × Historisk Accuracy

Varje signal baseras på tre oberoende faktorer:

| Faktor | Vad den mäter | Källa |
|--------|--------------|-------|
| **N1** | Trigger-träffsäkerhet | Hur ofta trigger-villkoret slår igenom |
| **N2** | Sektor-korrelation | Hur ofta riktningen stämmer med sektorn |
| **Historisk accuracy** | Kombinerad precision | Tidigare N1+N2-resultat för samma aktie/trigger |

**Varför multiplikation?**

- Alla tre faktorer måste vara starka för en hög confidence. En svag faktor drar ner hela score — precis som i verkligheten: en trigger som ofta slår men sällan har rätt sektordirection är inte pålitlig.
- Produkt ger naturlig "straff" för svaga länkar i kedjan. Summan skulle maskera problem.
- Resultatet landar i `[0, 1]` utan extra normalisering.

**Exempel:**
- 80% trigger + 75% sektor + 70% historik → `0.8 × 0.75 × 0.7 = 0.42` (styrka 3)
- 90% trigger + 40% sektor + 80% historik → `0.9 × 0.4 × 0.8 = 0.288` (styrka 2)

---

## Trösklar för styrka 1–5

| Styrka | Confidence | Beskrivning |
|--------|-----------|-------------|
| 5 | ≥ 0.70 | Mycket stark — alla faktorer är höga |
| 4 | ≥ 0.50 | Stark — pålitlig, men inte perfekt |
| 3 | ≥ 0.30 | Måttlig — agerbar, men med reservation |
| 2 | ≥ 0.15 | Svag — möjlig om man tolererar risk |
| 1 | < 0.15 | För svag — ingen signal genereras |

**Varför just dessa trösklar?**

- **0.70** — Två faktorer nära 0.85 eller alla tre över 0.90. Det är sällsynt och betyder stark överensstämmelse.
- **0.50** — Minst en faktor är svag, men de andra kompenserar. T.ex. `0.9 × 0.9 × 0.6 = 0.486` precis under — det är medvetet strikt.
- **0.30** — Två faktorer OK, en svag. `0.7 × 0.7 × 0.6 = 0.294`. Gränsen där signal fortfarande är agerbar.
- **0.15** — Nedre gräns för att överhuvudtaget fundera på att agera. `0.5 × 0.5 × 0.6 = 0.15` — alla faktorer halvbra.
- **Under 0.15** — För mycket osäkerhet. Chansen att två av tre faktorer är svaga är för hög.

Trösklarna är framtagna empiriskt genom att backtesta mot historisk data. De kan justeras om datamängden växer.

---

## Varför styrka 1 returnerar None

En signal med styrka 1 har confidence < 0.15. Det betyder att minst en av de tre faktorerna är kraftigt svag eller att alla tre är mediokra.

- Syftet med systemet är inte att generera signaler till varje pris — det är att generera *tillförlitliga* signaler.
- Att returnera `None` istället för en svag signal tvingar konsumenten att explicit hantera "avvaktar"-fallet.
- I Discord-rapporter och backtesting visas "avvaktar" istället för en signal — tydligare kommunikation.

---

## Köp/Sälj-riktning från trigger-riktning

| Trigger-riktning | Signal | Förklaring |
|------------------|--------|-----------|
| Bullish | **Köp** | Förväntad uppgång — gå lång |
| Bearish | **Sälj** | Förväntad nedgång — gå kort |
| Neutral | **None** | Ingen tydlig riktning — avvaktar |

Riktningen extraheras från trigger-texten via regelbaserad nyckelordsmatchning i `sector_analysis.py` (se `extract_direction()`). Det är enkel NLP — kontextberoende men täcker de vanligaste fallen.

---

## Edge Cases

### Noll accuracy (någon faktor = 0)

Produkten blir noll → confidence 0 → styrka 1 → `None`. Rätt hanterat — en faktor med noll träffsäkerhet förstör hela signalen.

### Saknad data

Om historisk accuracy saknas (t.ex. ny trigger) antas den vara 0.5 (neutral). Det ger konservativa signaler tills data byggs upp.

### Clamping

Alla inputs clampas till `[0, 1]` innan multiplikation:
- Negativa värden → 0.0
- Värden över 1.0 → 1.0

Det skyddar mot korrupt data eller beräkningsfel.

### Position size och P&L

Hypotetisk P&L beräknas som:

- **Köp-signal:** `pnl_pct = (exit - entry) / entry × 100`
- **Sälj-signal:** `pnl_pct = -(exit - entry) / entry × 100` (inverterat — vinst om pris faller)
- **Belopp:** `position_size × pnl_pct/100 × entry_price`

Edge case: `entry_price = 0` eller `None` → hoppar över signalen (division by zero-skydd).

---

## P&L-beräkningsmetodik

Systemet beräknar **hypotetisk** P&L — inte faktisk trading. Syftet är att utvärdera om signalerna hade varit lönsamma historiskt.

**Antaganden:**
- Entry till exit utan slippage eller transaktionskostnader
- Position size är konstant (eller anges explicit)
- Ingen hävstång

**Resultat:**
- `hypothetical_pnl_pct`: Procentuell avkastning
- `hypothetical_pnl_amount`: Absolut belopp givet position size
- `entry_price` / `exit_price`: Använda priser

Detta ger en rättvis bild av signalernas kvalitet utan att blanda in execution-risk.

---

*Senast uppdaterad: 2026-05-25*
