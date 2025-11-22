import asyncio
import websockets
import time
import requests
from collections import deque


# --- CONFIG ---
TELEGRAM_TOKEN = "8567422644:AAGsznOSLyaUAfmELTzSGE1820QjFh3dvSs"
CHAT_ID = "1516725477"

SYMBOL = "1HZ100V"   # Can change to R_75, R_50 etc.

MAX_HISTORY = 25
CHAOS_JUMP_THRESHOLD = 5
CHAOS_VARIANCE_THRESHOLD = 4
MIN_CLUSTER_REPEATS = 2

# --- TELEGRAM SEND ---
def alert(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    requests.post(url, json=payload)


# --- CHAOS DETECTION ---
def detect_chaos(digits, speeds):
    if len(digits) < 10:
        return None  # Not enough info yet

    avg_speed = sum(speeds) / len(speeds)
    speed_chaos = avg_speed < 0.08

    jumps = [abs(digits[i] - digits[i-1]) for i in range(1, len(digits))]
    big_jumps = sum(1 for j in jumps if j >= CHAOS_JUMP_THRESHOLD)
    jumps_chaos = big_jumps >= 5

    spread = len(set(digits))
    spread_chaos = spread >= CHAOS_VARIANCE_THRESHOLD

    repeats = sum(1 for i in range(1, len(digits)) if digits[i] == digits[i-1])
    cluster_missing = repeats < MIN_CLUSTER_REPEATS

    chaos_score = sum([speed_chaos, jumps_chaos, spread_chaos, cluster_missing])
    return chaos_score >= 3


# --- MAIN ---
async def run():
    url = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    history = deque(maxlen=MAX_HISTORY)
    speeds = deque(maxlen=MAX_HISTORY)
    last_time = time.time()

    last_state = None  # None / SAFE / CHAOS

    async with websockets.connect(url) as ws:
        await ws.send(f'{{"ticks":"{SYMBOL}"}}')
        alert("📡 Digit Watcher started…")

        while True:
            msg = await ws.recv()
            data = eval(msg)

            tick = float(data["tick"]["quote"])
            digit = int(str(tick)[-1])

            now = time.time()
            speeds.append(now - last_time)
            last_time = now

            history.append(digit)

            is_chaos = detect_chaos(list(history), list(speeds))

            # First stable state
            if is_chaos is False and last_state != "SAFE":
                alert("🟢 SAFE MARKET — Strong digit pattern.\nGood time to trade.")
                last_state = "SAFE"

            # First chaotic state
            if is_chaos is True and last_state != "CHAOS":
                alert("🔴 CHAOS DETECTED — Market too unstable.\nDO NOT trade now.")
                last_state = "CHAOS"

            await asyncio.sleep(0)


asyncio.run(run())
