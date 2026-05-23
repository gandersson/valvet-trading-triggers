#!/usr/bin/env python3
"""Testa Discord webhook — skicka ett testmeddelande"""

import asyncio
import aiohttp
from datetime import datetime

WEBHOOK_URL = "https://discord.com/api/webhooks/1507670079159009361/TtYim856aiFAV-626MYCtMGln12x4QpJcrRNb4DjQicSMLga4lzn1nFRVAvFtrKiOnBk"

async def send_test():
    embed = {
        "title": "🧪 Test — Trading Triggers Webhook",
        "description": "Detta är ett testmeddelande. Om du ser detta fungerar webhooken! 🎉",
        "color": 0x00FF00,
        "fields": [
            {
                "name": "⏰ Tid",
                "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S CET'),
                "inline": True
            },
            {
                "name": "🔧 Status",
                "value": "Webhook konfigurerad ✅",
                "inline": True
            }
        ],
        "footer": {
            "text": "Valvet Trading Triggers 🤖"
        }
    }
    
    payload = {"embeds": [embed]}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(WEBHOOK_URL, json=payload) as resp:
            if resp.status == 204:
                print("✅ Testmeddelande skickat till Discord!")
                print("   Kolla i #trading-triggers kanalen")
            else:
                print(f"❌ Fel: {resp.status}")
                print(await resp.text())

if __name__ == "__main__":
    asyncio.run(send_test())
