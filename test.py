import websocket

url = "wss://et.af-south-1.spribegaming.com/api/v2/public/et-player-stomp/407/bnqjvgpe/websocket?currency=KES&userId=78308e8140-167175-545673-7b8007-8d1bb5ba59fc&token=zgjN2YTNzYzNx0yYmlTNhJWNiJWMkhTL3ADM4I2NtMzN2UDN10SN3EzN2ETLwQTM4UGOwMDO30yM2YGZwUWOhRWZxEjZ3kTM5ETZ1QTO3gzN2UTOhJjYwkjZ2kTZxEGN&operator=odibets_af&sessionToken=T9SVahYfqLRQ9ZsK60MdIvvbFXgezEQ0OLFaCaBHTL7XOZw7MHh5NsQin9M6SmUo&deviceType=desktop&gameIdentifier=AVIATOR&gameZone=aviator_core_inst14_af&lang=en"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://odibets.com",
}

def on_message(ws, message):
    print("Message:", message)

def on_error(ws, error):
    print("Error:", error)

def on_close(ws):
    print("Closed connection")

def on_open(ws):
    print("Connected!")

ws = websocket.WebSocketApp(
    url,
    header=[f"{k}: {v}" for k, v in headers.items()],
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()
