import asyncio
import websockets
import json


API_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"
import asyncio, json, websockets
import threading
class Balance:
    def __init__(self, token=None):
        self.token = token
        self.curr_balance = None
        self.running = False
        # Start the event loop in a background thread
        thread = threading.Thread(target=self._start_loop, daemon=True)
        thread.start()

    def _start_loop(self):
        asyncio.run(self.monitor_balance())

    async def monitor_balance(self):
        self.running=True
        while self.running:
            async with websockets.connect("wss://ws.derivws.com/websockets/v3?app_id=1089") as ws:
                # Authorize
                await ws.send(json.dumps({"authorize": self.token}))
                auth_response = json.loads(await ws.recv())
                print("Authorized:", auth_response["authorize"]["loginid"])

                # Subscribe to balance updates
                await ws.send(json.dumps({"balance": 1, "subscribe": 1}))

                # Continuously listen for balance updates
                while self.running:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                        if msg.get("msg_type") == "balance":
                            balance = msg["balance"]["balance"]
                            currency = msg["balance"]["currency"]
                            self.curr_balance = balance
                            print(f"Balance update: {balance} {currency}")
                    except asyncio.TimeoutError as ex:
                        print("*" * 50, "\nError fetching balance", ex)
                        break # re-authorize
        self.running= False

async def run_bot(symbol="1HZ100V", ticks_to_trade=6, barrier=1, amount=1, contract_type="DIGITDIFF"):
    async with websockets.connect(API_URL) as ws:
        # Authenticate first
        await ws.send(json.dumps({"authorize": '6aRpjKXBIQc51GC'}))
        auth = await ws.recv()
        count = 0
        
        for count in range(ticks_to_trade):
                
                if count % 2 == 0:
                    amount *=2
                else:
                    amount /=2
                # print(f"Tick {count}: {tick['quote']}")

                # Buy immediately without waiting for previous trade to finish
                await ws.send(json.dumps({
                    "buy": 1,
                    "price": amount,
                    "parameters": {
                        "contract_type": contract_type,
                        "symbol": symbol,
                        "duration": 1,
                        "duration_unit": "t",
                        "basis": "stake",
                        "amount": amount,
                        "currency": "USD",
                        "barrier": barrier
                    }
                }))

                if count >= ticks_to_trade:
                    break
                asyncio.sleep(1)
def run(symbol="1HZ100V", amount=1, barrier=1, ticks=5, contract_type="DIGITDIFF"):
    asyncio.run(run_bot(symbol=symbol, amount=amount, barrier=barrier, ticks_to_trade=ticks, contract_type=contract_type))

# Eliminated latency

if __name__ == "__main__":
    run()