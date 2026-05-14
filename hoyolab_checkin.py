#!/usr/bin/env python3
"""
HoYoLAB Genshin Impact Daily Check-In Automation
=================================================
Automatically claims your daily HoYoLAB check-in reward for Genshin Impact.

Requirements:
    pip install requests schedule

Usage:
    1. Fill in your cookie values in the CONFIG section below.
    2. Run once:        python hoyolab_checkin.py --once
    3. Run on schedule: python hoyolab_checkin.py --schedule

How to get your cookies (ltoken_v2 & ltuid_v2):
    1. Go to https://www.hoyolab.com and log in.
    2. Open DevTools (F12) → Console tab.
    3. Paste and run this snippet:
         let c = document.cookie.split(';').map(v => v.trim().split('='));
         console.log(c.map(([k,v]) => ['ltuid_v2','ltoken_v2'].includes(k) ? `${k}=${v};` : null).filter(v=>v).join(' '));
    4. Copy the output: e.g. ltuid_v2=12345678; ltoken_v2=v2_xxxx...;
    5. Paste the values into CONFIG below.

SECURITY: Never share your cookie values with anyone.
NOTE: Logging out of HoYoLAB will invalidate your cookies.
"""

import requests
import schedule
import time
import argparse
import logging
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIG — fill in your values here
# ─────────────────────────────────────────────
CONFIG = {
    # Your HoYoLAB cookie values (see instructions above)
    "ltuid_v2":   "LTUID_V2",
    "ltoken_v2":  "LTOKEN_V2",
    # Schedule time in HH:MM format (server resets at 00:00 UTC+8 / 16:00 UTC)
    # Default: 16:05 UTC (5 min after reset) — adjust for your timezone
    "checkin_time": "22:00",
}
# ─────────────────────────────────────────────

# HoYoLAB API constants
CHECKIN_URL    = "https://sg-hk4e-api.hoyolab.com/event/sol/sign"
REWARD_URL     = "https://sg-hk4e-api.hoyolab.com/event/sol/home"
INFO_URL       = "https://sg-hk4e-api.hoyolab.com/event/sol/info"
ACT_ID         = "e202102251931481"
LANG           = "zh-cn"

HEADERS = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer":      "https://act.hoyolab.com/",
    "Origin":       "https://act.hoyolab.com",
    "Content-Type": "application/json",
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def build_cookie(cfg: dict) -> str:
    return f"ltuid_v2={cfg['ltuid_v2']}; ltoken_v2={cfg['ltoken_v2']};"


def get_checkin_info(cookie: str) -> dict | None:
    """Fetch current check-in status (days checked, today's claimed status)."""
    try:
        resp = requests.get(
            INFO_URL,
            params={"act_id": ACT_ID, "land": LANG},
            headers={**HEADERS, "Cookie": cookie},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("retcode") == 0:
            return data.get("data", {})
    except requests.RequestException as e:
        log.error(f"Failed to fetch check-in info: {e}")
    return None


def get_todays_reward(cookie: str) -> str:
    """Fetch today's reward name from the rewards calendar."""
    try:
        resp = requests.get(
            REWARD_URL,
            params={"act_id": ACT_ID},
            headers={**HEADERS, "Cookie": cookie},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        awards = data.get("data", {}).get("awards", [])
        if awards:
            # Today is determined by current month day (1-indexed)
            today_index = datetime.now().day - 1
            reward = awards[today_index % len(awards)]
            return f"{reward.get('name', '?')} x{reward.get('cnt', '?')}"
    except requests.RequestException as e:
        log.error(f"Failed to fetch reward info: {e}")
    return "Unknown Reward"


def checkin(cookie: str) -> tuple[bool, str]:
    """
    Perform the daily check-in.
    Returns (success: bool, message: str).
    """
    try:
        resp = requests.post(
            CHECKIN_URL,
            params={"lang": LANG},
            json={"act_id": ACT_ID},
            headers={**HEADERS, "Cookie": cookie},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        code = data.get("retcode")
        msg  = data.get("message", "")

        if code == 0:
            return True, "Check-in successful!"
        elif code == -5003:
            return True, "Already checked in today."
        else:
            return False, f"Check-in failed (code {code}): {msg}"

    except requests.RequestException as e:
        return False, f"Request error: {e}"


def send_discord_notification(webhook_url: str, title: str, description: str, success: bool):
    """Send a Discord embed notification."""
    if not webhook_url:
        return
    color = 0x4CAF50 if success else 0xF44336  # green / red
    payload = {
        "embeds": [{
            "title":       title,
            "description": description,
            "color":       color,
            "footer":      {"text": "HoYoLAB Auto Check-In"},
            "timestamp":   datetime.utcnow().isoformat(),
        }]
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        log.info("Discord notification sent.")
    except requests.RequestException as e:
        log.warning(f"Discord notification failed: {e}")


def validate_config(cfg: dict) -> bool:
    """Basic sanity check on config values."""
    if cfg["ltuid_v2"] == "YOUR_LTUID_V2_HERE" or cfg["ltoken_v2"] == "YOUR_LTOKEN_V2_HERE":
        log.error("⛔ Please fill in your ltuid_v2 and ltoken_v2 in the CONFIG section.")
        return False
    if not cfg["ltuid_v2"].isdigit():
        log.warning("ltuid_v2 looks unusual — expected a numeric string.")
    if not cfg["ltoken_v2"].startswith("v2_"):
        log.warning("ltoken_v2 doesn't start with 'v2_' — double-check your cookie.")
    return True


def run_checkin():
    """Main check-in routine — called on schedule or directly."""
    log.info("═" * 50)
    log.info("Starting HoYoLAB Genshin Impact daily check-in")
    log.info("═" * 50)

    if not validate_config(CONFIG):
        return

    cookie = build_cookie(CONFIG)

    # Fetch pre-check-in info
    info = get_checkin_info(cookie)
    if info:
        total_days = info.get("total_sign_day", "?")
        log.info(f"📅 Total check-in days so far: {total_days}")
        if info.get("is_sign"):
            log.info("ℹ️  Already signed in today — skipping API call.")
            '''
            send_discord_notification(
                CONFIG["discord_webhook"],
                "🌸 Genshin Daily Check-In",
                "Already checked in today!",
                success=True,
            )
            '''
            return

    # Fetch today's reward
    reward = get_todays_reward(cookie)
    log.info(f"🎁 Today's reward: {reward}")

    # Perform check-in
    success, message = checkin(cookie)

    if success:
        log.info(f"✅ {message}")
        log.info(f"🎉 Reward claimed: {reward}")
    else:
        log.error(f"❌ {message}")

    # Discord notification
    '''
    send_discord_notification(
        CONFIG["discord_webhook"],
        "🌸 Genshin Daily Check-In",
        f"{message}\n🎁 Reward: **{reward}**",
        success=success,
    )
    '''

    log.info("═" * 50)


def run_scheduled():
    """Run check-in on a daily schedule."""
    checkin_time = CONFIG.get("checkin_time", "16:05")
    log.info(f"⏰ Scheduled daily check-in at {checkin_time} (local time).")
    log.info("   Press Ctrl+C to stop.\n")

    schedule.every().day.at(checkin_time).do(run_checkin)

    # Run immediately on first start too
    run_checkin()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HoYoLAB Genshin Daily Check-In Bot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once",     action="store_true", help="Run check-in once and exit")
    group.add_argument("--schedule", action="store_true", help="Run on daily schedule (default)")
    args = parser.parse_args()

    if args.once:
        run_checkin()
    else:
        # Default to scheduled mode
        run_scheduled()
