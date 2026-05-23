#!/bin/bash
# Trading Triggers - Kör med Discord webhook
# Detta script sätter webhook-URL och kör trigger-systemet
# Bestämmer evaluation_time baserat på aktuell timme:
#   16-17 → 1h
#   18-19 → 2h
#   22-23 → EOD

cd "$(dirname "$0")"

# Discord webhook URL (från #trading-triggers kanal)
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/1507670079159009361/TtYim856aiFAV-626MYCtMGln12x4QpJcrRNb4DjQicSMLga4lzn1nFRVAvFtrKiOnBk"

# Bestäm evaluation_time baserat på aktuell timme (CET)
HOUR=$(date +%H)
if [[ "$HOUR" -ge 16 && "$HOUR" -lt 18 ]]; then
    export EVALUATION_TIME="1h"
elif [[ "$HOUR" -ge 18 && "$HOUR" -lt 22 ]]; then
    export EVALUATION_TIME="2h"
elif [[ "$HOUR" -ge 22 && "$HOUR" -lt 24 ]]; then
    export EVALUATION_TIME="EOD"
else
    export EVALUATION_TIME="1h"
fi

echo "Kör med EVALUATION_TIME=$EVALUATION_TIME (HOUR=$HOUR)"

# Aktivera virtual environment
source .venv/bin/activate

# Kör trigger-systemet
python src/trigger_system_v1.py
