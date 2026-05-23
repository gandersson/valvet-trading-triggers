#!/bin/bash
# Trading Triggers LaunchAgent — körs vid schemalagda tider
# Bestämmer evaluation_time baserat på aktuell timme:
#   16-17 → 1h
#   18-19 → 2h
#   22-23 → EOD

# Sätt miljö
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
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

echo "[$(date)] Kör med EVALUATION_TIME=$EVALUATION_TIME (HOUR=$HOUR)" >> /tmp/trading-triggers.log

# Gå till projektkatalogen
cd /Users/xandgo/.openclaw/workspace/projects/trading-triggers

# Aktivera venv och kör
source .venv/bin/activate
python src/trigger_system_v1.py >> /tmp/trading-triggers.log 2>&1
