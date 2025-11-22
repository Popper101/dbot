from flask import Flask, render_template, request, jsonify, redirect, flash, Response
import analysis
import requests
import winsound
import threading
import time
import asyncio
import json
from bulk import Balance
from deriv_client import DerivClient, DerivTicks, TOKENS
from user import Users
import hashlib # for uniquely identifying users
from itertools import groupby # finding streaks in digits
app = Flask(__name__)
app.secret_key = "hahahaha;/"  # Needed for flash messages

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

deriv_client = DerivClient(token=TOKENS["API_TOKEN_DEMO"])
balance_obj = Balance(token=TOKENS["API_TOKEN_DEMO"])

async def start_deriv():
    await deriv_client.connect()
    await deriv_client.ensure_connected()
    loop.create_task(deriv_client.keepalive())

def start_loop():
    asyncio.set_event_loop(loop)
    loop.create_task(start_deriv())
    loop.run_forever()

threading.Thread(target=start_loop, daemon=True).start()


# Ticks
# Define the symbols you want
volatilities = [10,25,50, 75, 100]
SYMBOLS = [f"1HZ{x}V" for x in volatilities] +[f"1HZ{x}V" for x in [15,30,90]]#+ [f"JD{x}" for x in volatilities]

# Create DerivTicks instance
ticks_client = DerivTicks(SYMBOLS, token=TOKENS["API_TOKEN_DEMO"])

def start_ticks_loop():
    asyncio.run(ticks_client.subscribe_all())

# Start background thread for WebSocket
threading.Thread(target=start_ticks_loop, daemon=True).start()
#
## End threads

#%% Users
def get_device_fingerprint():
    ua_string = request.user_agent.string or ""
    ip = request.remote_addr or ""
    raw = f"{ua_string}|{ip}"
    # print("User fingerprint raw:", raw)
    return hashlib.sha256(raw.encode()).hexdigest()

users = Users()
def get_user():
    global users
    user_fingerprint = get_device_fingerprint()
    return users.add_user(user_fingerprint)
#
## End Users
def check_market():
    url = "http://localhost:5000/best_matchers"
    data = requests.get(url).json()
    # sort the symbols by best performing one
    data = dict(
        sorted(
            data.items(),
            key=lambda x: sum(d['avg'] for d in x[1].values()) / len(x[1]),
            reverse=False  # lowest avg first
        )
    )
    best_symbol = list(data)[0]
    best_keys = list(data[best_symbol])
    best_res = data[best_symbol][best_keys[0]]['avg']
    return best_res


#
##  end threaded functions
@app.route("/check-market")
def market_check():
    value = check_market()
    return jsonify({"value": value})
@app.route('/stats')
def show_stats():
    all_outcomes = analysis.run()
    # filter barriers so that only 4,5,6 are included. You can extract the barriers from such keys: "(4, 'oou')": {
    filtered_outcomes = {}

    for symbol, outcomes in all_outcomes.items():
        # Keep only outcomes whose key starts with (4,), (5,) or (6,)
        filtered_outcomes[symbol] = [
            outcome for outcome in outcomes
            if int(list(outcome.keys())[0].split(',')[0].strip('(')) in (4, 5, 6,3,7)
        ]

    # filtered_outcomes = {k:v for k, v in all_outcomes.items() if k in ['1HZ25V', '1HZ50V']}
    return render_template('stats.html', all_outcomes=filtered_outcomes)

@app.route('/stats/overunder')
def show_stats_over_under():
    try:
        url = "http://localhost:5000/best_all"
        data = requests.get(url).json()
        return render_template("overunder.html", stats=data)
    except Exception as ex:
        return "<p>Connection not established</p>"

@app.route("/stats/matchersdiffers")
def volatility_stats():
    url = "http://localhost:5000/best_matchers"
    data = requests.get(url).json()
    # sort the symbols by best performing one
    data = dict(
        sorted(
            data.items(),
            key=lambda x: sum(d['avg'] for d in x[1].values()) / len(x[1]),
            reverse=False  # lowest avg first
        )
    )

    return render_template("matchersdiffers.html", stats=data)

@app.route('/growth', methods=['GET', 'POST'])
def growth():
    table = []
    initial_balance = None
    target_multiplier = None

    if request.method == 'POST':
        try:
            initial_balance = float(request.form['balance'])
            target_multiplier = float(request.form['multiplier'])
            stake = initial_balance * 0.1  # 10% stake
            days = 50  # you can change this
            balance = initial_balance

            for day in range(1, days + 1):
                profit = balance * (target_multiplier - 1)
                stake  = balance * 0.1
                expected_balance = balance + profit
                table.append({
                    "day": day,
                    "balance": round(balance, 2),
                    "profit": round(profit, 2),
                    "stake": round(stake, 2),
                    "expected_balance": round(expected_balance, 2)
                })
                balance = expected_balance
        except ValueError:
            pass

    return render_template(
        'growth.html',
        table=table,
        initial_balance=initial_balance,
        target_multiplier=target_multiplier
    )

@app.route("/widget")
def widget():
    return render_template("widget.html")
@app.route("/trade", methods=["POST"])
def trade():
    symbol = request.form["symbol"]
    digit = float(request.form["digit"])
    amount = float(request.form["amount"])
    ticks = int(request.form["ticks"])
    # Run trade asynchronously in background thread
    thread = threading.Thread(
        target=run_trade,
        kwargs={
            "symbol": symbol,
            "amount": amount,
            "barrier": digit,
            "ticks": ticks
        },
        daemon=True  # ensures it won't block app shutdown
    )
    thread.start()
    print(symbol, digit, amount, ticks)
    return redirect("/stats/matchersdiffers") 

@app.route("/max-ticks", methods=["POST"])
def set_max_ticks():
    user = get_user()
    max_ticks = int(request.form['max_ticks'])
    user.max_ticks = max_ticks
    return jsonify({"status":"ok", "message": f"max ticks set to {max_ticks}"})


def run_trade(symbol="1HZ100V", ticks=6, barrier=1, amount=1, contract_type="DIGITDIFF"):
    """Submit trade coroutine to the running event loop safely."""
    async def trade_task():
        try:
            result = await deriv_client.buy(symbol=symbol, contract_type=contract_type, barrier=barrier, amount=amount, ticks_to_trade=ticks)
            print(f"✅ Trade completed: {result}")
        except Exception as e:
            print(f"❌ Trade error: {e}")

    # Submit coroutine to global loop
    asyncio.run_coroutine_threadsafe(trade_task(), loop)



@app.route("/bulk-trades", methods=["GET", "POST"])
def bulk_trades():
    global SYMBOLS
    symbols = SYMBOLS
    contract_types = ["DIGITDIFF", "DIGITMATCH", "DIGITOVER", "DIGITUNDER", "DIGITEVEN", "DIGITODD"]

    if request.method == "POST":
        # Get form data
        symbol = request.form.get("symbol")
        contract_type = request.form.get("contract_type")
        barrier = int(request.form.get("barrier"))
        stake = float(request.form.get("stake"))
        ticks = int(request.form.get("ticks"))
        

        # Start async trade in background thread (non-blocking)
        thread = threading.Thread(
            target=run_trade,
            kwargs=dict(symbol=symbol, contract_type=contract_type, barrier=barrier, amount=stake, ticks=ticks)
        )
        thread.daemon = True
        thread.start()

        message = f"Trade started: {contract_type} on {symbol} (Barrier {barrier}) — {ticks} ticks at ${stake}"
        flash(message)

        # return render_template(
        #     "trade.html",
        #     symbols=symbols,
        #     contract_types=contract_types,
        #     contract_type=contract_type,
        #     barrier=barrier,
        #     stake=stake,
        #     ticks=ticks,
        #     symbol=symbol,
        #     message=message
        # )
        return jsonify({"message":message})

    return render_template("trade.html", symbols=symbols, contract_types=contract_types)
@app.route("/balance")
def get_balance():
    global balance
    # You can cache this from your websocket thread or query it directly
    balance = balance_obj.curr_balance
    return jsonify({"balance": balance})


@app.route("/last-tick")
def last_tick():
    user = get_user()
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing symbol parameter"}), 400

    tick = ticks_client.last_ticks.get(symbol)
    if tick is None:
        return jsonify({"error": f"No data yet for {symbol}"}), 404
    tick = tick[-user.max_ticks: ]
    total = len(tick)
    percentages_overs = {d: f"{sum(1 for x in tick if int(x) > d)*100/ total:.2f}" if total >0 else 0 for d in range(9)}
    percentages_unders = {d: f"{sum(1 for x in tick if int(x) < d)*100/ total:.2f}" if total >0 else 0 for d in range(1,10)}
    percentages = {x: f"{tick.count(str(x))*100/total:.2f}" if total >0 else 0 for x in range(10)}
    odd_count = sum(1 for x in tick if int(x) %2 != 0)
    even_count = total - odd_count
    odd_pct, even_pct = round(odd_count*100/total, 2) if total >0 else 0, round(even_count*100/total,2) if total > 0 else 0
    barrier = request.args.get("barrier", 4, type=int)
    tick_cursor = tick[-5:]
    total_cursor = len(tick_cursor)
    over_pct = sum(1 for x in tick_cursor if int(x) > barrier)/total_cursor*100 if total_cursor >0 else 0
    under_pct = sum(1 for x in tick_cursor if int(x) < barrier)/total_cursor*100 if total_cursor >0 else 0
    return jsonify({
        "symbol": symbol,
        "last_tick": tick[-1] if len(tick)> 0 else 0,
        "even_odd_list": ['E' if int(x) %2 ==0 else 'O' for x in tick],
        "over_under_list": ['O' if int(x) >barrier else 'U' if int(x) < barrier else 'E' for x in tick],
        "percentages": percentages,
        "total": total,
        "even_odd": {"oddCount": odd_count, "evenCount": even_count, "oddPercent": odd_pct, "evenPercent": even_pct},
        "percentages_overs": percentages_overs,
        "percentages_unders": percentages_unders,
        "percentages_cursor": {"over":round(over_pct), "under":round(under_pct)} 
    })

@app.route("/last-ticks")
def last_ticks():
    user = get_user()
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing symbol parameter"}), 400

    tick = ticks_client.last_ticks.get(symbol)
    tick = [int(x) for x in tick]
    if tick is None:
        return jsonify({"error": f"No data yet for {symbol}"}), 404
    tick = tick[-user.max_ticks: ]
    return jsonify({
        "symbol": symbol,
        "last_ticks": tick,
    })
# Fetch the best symbol
@app.route("/fetch-best-symbol", methods=["POST"])
def on_right_click():
    '''
    Fetches the best symbol based on contract type
    '''
    user = get_user()
    data = request.get_json()
    ctype = data.get("contract_type")
    print(f"Right-clicked on {ctype}")
    
    if ctype in ["DIGITMATCH", "DIGITDIFF"]:
        symbols = ticks_client.symbols
        best_percentages = {s: 0 for s in symbols}
        func = min if ctype == "DIGITDIFF" else max
        for symbol in symbols:
            tick = ticks_client.last_ticks.get(symbol)
            if tick is None:
                return jsonify({"error": f"No data yet for {symbol}"}), 404
            tick = tick[-user.max_ticks: ]
            total = len(tick)
            percentages = {x: f"{tick.count(str(x))*100/total:.2f}" if total >0 else 0 for x in range(10)}
            min_percentage = func(percentages.items(), key=lambda x: float(x[1]))
            best_percentages[symbol] = min_percentage
        
        # get best performing symbol
        best_symbol, (best_digit, _) = func(best_percentages.items(), key=lambda x: x[1][1])
        return jsonify({"status": "ok", "symbol": best_symbol, "message": "Extracted best differs", "digit": int(best_digit)})

    elif ctype in ["DIGITEVEN", "DIGITODD"]:
        symbols = getattr(ticks_client, "symbols", []) or []
        best_even = {}
        best_odd = {}

        # iterate symbols, compute even/odd percentages using last user.max_ticks ticks
        for symbol in symbols:
            ticks = ticks_client.last_ticks.get(symbol) or []
            # limit to last max_ticks if provided and > 0
            if getattr(user, "max_ticks", None):
                max_t = int(user.max_ticks) if int(user.max_ticks) > 0 else None
            else:
                max_t = None
            ticks = ticks[-max_t:] if max_t else ticks

            total = len(ticks)
            if total == 0:
                # no data for this symbol — skip it
                continue

            even_count = 0
            for t in ticks:
                try:
                    # if tick is the whole quote like '123.45' and you want last digit:
                    # digit = int(str(t)[-1])
                    # otherwise if tick is already a digit string/number use int(t)
                    digit = int(t)  # adjust if t contains more than a digit
                except Exception:
                    # try fallback: take last character
                    try:
                        digit = int(str(t).strip()[-1])
                    except Exception:
                        # cannot parse this tick — skip this tick
                        continue

                if digit % 2 == 0:
                    even_count += 1

            # recompute total as number of ticks we successfully parsed
            parsed_total = total  # or count of successfully parsed ticks if you changed above
            if parsed_total == 0:
                continue

            even_pct = (even_count * 100.0) / parsed_total
            odd_pct = 100.0 - even_pct

            best_even[symbol] = even_pct
            best_odd[symbol] = odd_pct

        # if no symbols had valid ticks
        if not best_even and not best_odd:
            return jsonify({"error": "No tick data available for any symbol"}), 404

        # choose best depending on contract type
        if ctype == "DIGITEVEN":
            # choose symbol with the highest even percentage
            best_symbol, best_pct = max(best_even.items(), key=lambda kv: kv[1])
        else:  # DIGITODD
            best_symbol, best_pct = max(best_odd.items(), key=lambda kv: kv[1])

        return jsonify({
            "status": "ok",
            "symbol": best_symbol,
            "contract_type": ctype,
            "pct": round(best_pct, 2),
            "message": f"Extracted best {ctype}:{best_symbol}@{best_pct:.2f}"
        })

    elif ctype in ["DIGITOVER", "DIGITUNDER"]:
        digit = data.get("barrier", 4)
        symbols = ticks_client.symbols
        best_percentages_over = {s: 0 for s in symbols}
        best_percentages_under = {s: 0 for s in symbols}
        for symbol in symbols:
            tick = ticks_client.last_ticks.get(symbol)
            if tick is None or tick == []:
                return jsonify({"error": f"No data yet for {symbol}"}), 404
            tick = tick[-user.max_ticks: ]
            total = len(tick)
            pct_over = sum(1 for x in tick if int(x) > digit) *100/total
            pct_under = sum(1 for x in tick if int(x) < digit) *100/total
            best_percentages_over[symbol] = pct_over
            best_percentages_under[symbol] = pct_under
        
        # get best performing symbol
        best_symbol2, best_pct = max(best_percentages_over.items(), key=lambda x: x[1])
        best_symbol1, best_pct1 = max(best_percentages_under.items(), key=lambda x: x[1])
        
        # if best_pct > best_pct1:
        #     best_contract = "DIGITOVER"
        #     best_symbol = best_symbol2
            
        # else:
        #     best_contract = "DIGITUNDER"
        #     best_symbol = best_symbol1
        #     best_pct = best_pct1
        if ctype == "DIGITOVER":
            best_contract = "DIGITOVER"
            best_symbol = best_symbol2
            best_pct = best_pct
        else:
            best_contract = "DIGITUNDER"
            best_symbol = best_symbol1
            best_pct = best_pct1
        
        return jsonify({"status": "ok", "symbol": best_symbol, "digit": digit, "contract_type":best_contract, "pct":best_pct, "message": f"Extracted best {ctype}@{digit}"})
    elif ctype in ["SWITCHOVER", "SWITCHUNDER"]:
        digit = int(data.get("barrier", 4))
        other_digit = 9-digit
        symbols = ticks_client.symbols
        best_percentages_over = {s: 0 for s in symbols}
        best_percentages_under = {s: 0 for s in symbols}
        for symbol in symbols:
            tick = ticks_client.last_ticks.get(symbol)
            if tick is None or tick == []:
                return jsonify({"error": f"No data yet for {symbol}"}), 404
            tick = tick[-user.max_ticks: ]
            total = len(tick)
            pct_over = sum(1 for x in tick if int(x) > digit and int(x) < other_digit) *100/total
            pct_under = sum(1 for x in tick if int(x) < digit and int(x) > other_digit) *100/total
            best_percentages_over[symbol] = pct_over
            best_percentages_under[symbol] = pct_under
        
        # get best performing symbol
        best_symbol2, best_pct = max(best_percentages_over.items(), key=lambda x: x[1])
        best_symbol1, best_pct1 = max(best_percentages_under.items(), key=lambda x: x[1])
        
        # if best_pct > best_pct1:
        #     best_contract = "DIGITOVER"
        #     best_symbol = best_symbol2
            
        # else:
        #     best_contract = "DIGITUNDER"
        #     best_symbol = best_symbol1
        #     best_pct = best_pct1
        if ctype == "SWITCHOVER":
            best_contract = "DIGITOVER"
            best_symbol = best_symbol2
            best_pct = best_pct
        else:
            best_contract = "SWITCHUNDER"
            best_symbol = best_symbol1
            best_pct = best_pct1
        
        return jsonify({"status": "ok", "symbol": best_symbol, "digit": digit, "contract_type":best_contract, "pct":best_pct, "message": f"Extracted best {ctype}@{digit}"})

    return jsonify({"status": "ok", "clicked": ctype})

# graph functions
@app.route("/stats/ticks", methods=["POST", "GET"])
def stats_ticks():
    global SYMBOLS
    # Update tick_counts dynamically in your actual code
    if request.method == "POST":
        try:
            symbol = request.form.get("symbol")
            num_ticks = int(request.form.get("ticks_count"))
            tick = ticks_client.last_ticks.get(symbol)
            if tick is None:
                return jsonify({"status":"ok", "message": f"No data yet for {symbol}"})
            tick = tick[-num_ticks:]
            total = len(tick)
            percentages = {x: round(tick.count(str(x))*100/total, 2) if total >0 else 0 for x in range(10)}
            
            return jsonify({"status": "ok", "data":percentages, "total": total})
        except Exception as ex:
            return jsonify({"status":"failed", "message": ex})

    return render_template("tickstats.html", symbols=SYMBOLS)

# graph functions
@app.route("/stats/ticks/overunder", methods=["POST", "GET"])
def stats_ticks_overunder():
    global SYMBOLS
    # Update tick_counts dynamically in your actual code
    if request.method == "POST":
        try:
            symbol = request.form.get("symbol")
            num_ticks = int(request.form.get("ticks_count"))
            tick = ticks_client.last_ticks.get(symbol)
            if tick is None:
                return jsonify({"status":"ok", "message": f"No data yet for {symbol}"})
            tick = tick[-num_ticks:]
            total = len(tick)
            percentages_overs = {x: round(sum(1 for t in tick if int(t) > x)*100/total if total >0 else 1,2) for x in range(10)}
            percentages_unders = {x: round(sum(1 for t in tick if int(t) < x)*100/total if total > 0 else 1,2) for x in range(10)}
            
            return jsonify({"status": "ok", "data":{"overs":percentages_overs, "unders": percentages_unders}, "total": total})
        except Exception as ex:
            return jsonify({"status":"failed", "message": ex})

    return render_template("tickstats.html", symbols=SYMBOLS)
#%% Utils section
def streak_stats(elements):
    streaks = [(el, sum(1 for _ in group)) for el, group in groupby(elements)]
    stats = {}
    for el in set(elements): # unique elements
        # extract the lengths of the elements
        lengths = [length for e, length in streaks if e == el]
        stats[el] = {
            "min_streak": min(lengths),
            "max_streak": max(lengths),
            "avg_streak": sum(lengths)/ len(lengths)
        }
    return stats

def get_streaks(elements, target_element):
    streaks = [(el, sum(1 for _ in group)) for el, group in groupby(elements)]
    target_streaks = [length for el, length in streaks if el == target_element]
    return target_streaks
@app.route("/stats/streak", methods=["GET"])
def streaks():
    user = get_user()
    max_ticks = user.max_ticks
    symbols = ticks_client.symbols
    symbol_streaks = {s: None for s in symbols}
    data_type = request.args.get("type", None)
    streak_type = request.args.get("streak_type", "even_odd") # even_odd or over_under
    for symbol in symbols:
        tick = ticks_client.last_ticks.get(symbol)
        data = tick[-max_ticks:]
        if streak_type == "over_under":
            barrier = int(request.args.get("barrier", 4))
            data = ['o' if int(t) >barrier else 'u' for t in data]
        elif streak_type == "even_odd":
            data = ['e' if int(t) % 2== 0 else 'o' for t in data]
        elif streak_type == "digits":
            data = [int(t) for t in data]
        streak = streak_stats(data)
        streak_data = dict(sorted(streak.items(), key=lambda x: x[1]['avg_streak'], reverse=True))
        symbol_streaks[symbol] = streak_data
    
    if data_type == "json":
        return jsonify(symbol_streaks) # return data as json
    # Render template and pass the dict
    return render_template("streaks.html", symbol_streaks=symbol_streaks)


#%% Bot section
@app.route("/bot/start", methods=["POST"])
def start_bot():
    user = get_user()
    if not user:
        return jsonify({"status": "error", "message": "User not authenticated"}), 401

    user.bot_running = True
    if deriv_client.bot is not None:
        if not deriv_client.bot.is_complete:
            return jsonify({
                "status": "already running",
                "message": f"Bot is already running"
            })
    # Extract form data from AJAX POST
    symbol = request.form.get("symbol")
    contract_type = request.form.get("contract_type")
    barrier = request.form.get("barrier", type=int)
    amount = request.form.get("stake", type=float)
    ticks = request.form.get("ticks", type=int)
    tp = request.form.get("tp", type=int)
    max_losses = request.form.get("max_losses", None, type=int)
    martingale = request.form.get("martingale", None, type=float)
    duration = request.form.get("duration", 1, type=float) # default is 1
    market_switch = True if request.form.get("market_switch", "off") == "on" else False
    contract_switch = True if request.form.get("contract_switch", "off") == "on" else False
    stop_loss = request.form.get("stop_loss", None, type=float)
    reverse_wait = request.form.get("reverse_wait", None, type=int)
    strategy = request.form.get("strategy", None, type=str)
    if tp == 1:
        tp = None
    max_losses = None if max_losses ==0 else max_losses
    print("strategy", strategy)
    
    # print("form", request.form)
    # Validate required parameters
    if not symbol or not contract_type or not amount or not ticks:
        return jsonify({"status": "error", "message": "Missing required parameters"}), 400

    async def trade_task():
        try:
            result = await deriv_client.buy_bot_strategy(
                symbol=symbol,
                contract_type=contract_type,
                barrier=barrier,
                amount=amount,
                ticks_to_trade=ticks,
                tp=tp,
                max_losses=max_losses,
                martingale=martingale,
                duration=duration,
                market_switch=market_switch,
                stop_loss=stop_loss,
                contract_switch=contract_switch,
                deriv_ticks=ticks_client,
                reverse_wait=reverse_wait,
                user=user,
                strategy=strategy
            )
            print(f"✅ Trade completed: {result}")
        except Exception as e:
            print(f"❌ Trade error: {e}")

    # Schedule the coroutine to run in background without blocking Flask
    asyncio.run_coroutine_threadsafe(trade_task(), loop)

    return jsonify({
        "status": "started",
        "message": f"Bot started for {symbol} ({contract_type}) with stake {amount} × {ticks} ticks."
    })


@app.route("/bot/stop", methods=["POST"])
def stop_bot():
    user = get_user()
    user.bot_running = False
    if deriv_client.bot is not None:
        print("Bot stopped")
        deriv_client.bot.is_complete = True
        deriv_client.bot.is_running = False
        return jsonify({"status": "stopped"})
    print("Bot stop failed")
    return jsonify({"status": "stopping failed"})

@app.route("/bot/status")
def bot_status():
    bot = deriv_client.bot
    return jsonify({
        "status": "ok",
        "runs": len(bot.trades),
        "total_staked": bot.total_staked,
        "total_pnl": sum(bot.pnl_hist),
        "trades": bot.trades,
        "wins": bot.wins,
        "losses": bot.losses,
        "is_complete": not bot.is_complete,
        "message": bot.message, # {"error": "message"} etc
        "bot_status" : bot.status
    })

#%% Accounts
@app.route("/account-change", methods=["POST"])
def change_account():
    global balance_obj, deriv_client

    account_type = request.json.get("type")
    user = get_user()
    account = "DEMO" if user.is_demo else "REAL"
    if account_type is not None:
        is_demo = account_type.upper() == "DEMO"
        balance_obj.token = user.change_account_type(is_demo=is_demo)
        balance_obj.running = False
        
        while balance_obj.running:
            time.sleep(2)
        token = balance_obj.token
        balance_obj = Balance(token=token)
        # 🔁 Switch DerivClient token asynchronously
        deriv_client.token = token # it will change automatically in it's keepalive
        # asyncio.run_coroutine_threadsafe(deriv_client.change_token(token), loop)
        account = "DEMO" if is_demo else "REAL"
        return jsonify({"status":"ok", "message": "account type changed", "account":account})
    return jsonify({"status":"failed", "message": "account type was not submitted", "account":account})

#%% Digit strengths
def check_strength_trend(digits, barrier=5, mode="over", window=10, steps=5):
    """
    Check the consistency of strength trend (increasing/decreasing)
    across multiple recent windows.

    Args:
        digits (list[int]): List of digits (oldest → newest)
        barrier (int): The threshold to compare digits against
        mode (str): "over" or "under"
        window (int): Window size for each percentage calculation
        steps (int): How many consecutive windows to check

    Returns:
        dict with:
            - pct_list: list of percentages for each window
            - avg_change: average % change between windows
            - consistency: % of changes going the same direction
            - trend: "increasing", "decreasing", "fluctuating"
    """
    total_needed = window * steps
    if len(digits) < total_needed:
        return {"error": f"Need at least {total_needed} digits for {steps} windows"}

    pct_list = []
    for i in range(steps):
        # progressively include more digits from the end
        end = len(digits)
        start = max(0, end - window * (i + 1))
        window_digits = digits[start:end]
        total = len(window_digits)
        
        if total == 0:
            continue  # skip to avoid zero division

        if mode == "over":
            pct = sum(d > barrier for d in window_digits) / total * 100
        elif mode == "under":
            pct = sum(d < barrier for d in window_digits) / total * 100
        elif mode == "even":
            pct = sum(d % 2 == 0 for d in window_digits) / total * 100
        elif mode == "odd":
            pct = sum(d % 2 != 0 for d in window_digits) / total * 100
        else:
            return {"error": f"Invalid mode: {mode}"}

        pct_list.append(pct)

    # reverse the list to get proper trend
    pct_list = list(reversed(pct_list))
    # Calculate consecutive differences
    diffs = [pct_list[i+1] - pct_list[i] for i in range(len(pct_list)-1)]
    avg_change = sum(diffs) / len(diffs)
    
    increasing = sum(d > 0 for d in diffs)
    decreasing = sum(d < 0 for d in diffs)
    consistency = max(increasing, decreasing) / len(diffs) * 100

    if consistency >= 60:  # e.g. 3 of 5 same direction
        trend = "increasing" if increasing > decreasing else "decreasing"
    else:
        trend = "fluctuating"

    return {
        "pct_list": [round(p, 2) for p in pct_list],
        "avg_change": round(avg_change, 2),
        "consistency": round(consistency, 1),
        "trend": trend
    }

@app.route("/stats/digit-strength", methods=["POST", "GET"])
def digit_strength():
    global SYMBOLS
    if request.method == "POST":
        try:
            symbol = request.form.get("symbol")
            barrier = int(request.form.get("barrier"))
            mode = request.form.get("mode")  # "over" or "under"
            window = int(request.form.get("window"))
            steps = int(request.form.get("steps"))

            tick = ticks_client.last_ticks.get(symbol)
            if tick is None:
                return render_template("digit_strength.html", symbols=SYMBOLS, status=f"No data for {symbol}", symbol=symbol, barrier=barrier, mode=mode, window=window, steps=steps)
            tick = [int(x) for x in tick]
            result = check_strength_trend(tick, barrier=barrier, mode=mode, window=window, steps=steps)
            return render_template("digit_strength.html", symbols=SYMBOLS, data=result, symbol=symbol, barrier=barrier, mode=mode, window=window, steps=steps)
        except Exception as ex:
            return render_template("digit_strength.html", symbols=SYMBOLS, status=f"Failed: {ex}", symbol=symbol, barrier=barrier, mode=mode, window=window, steps=steps)

    return render_template("digit_strength.html", symbols=SYMBOLS)

#%% Streaming
@app.route("/stream")
def stream():
    headers = {
                "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0"),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",  # marks it as AJAX-like
                "Referer": request.headers.get("Referer", "http://localhost:8000/"),
                "Origin": request.headers.get("Origin", "http://localhost:8000"),
            }
    def event_stream():
        while True:
            # If you’re using session auth (Flask-Login, cookies, etc.)

            try:
                response = requests.get(
                    "http://localhost:8000/stats/streak?type=json",
                    headers=headers,
                    timeout=5,
                )
                data = response.json()
                sorted_data = dict(
                    sorted(
                        data.items(),
                        key=lambda x: sum(d['avg_streak'] for d in x[1].values()) / len(x[1]),
                        reverse=True  # highest avg first
                    )
                )
                best_symbol = list(sorted_data)[0]
                best_avg_o, best_avg_e = round(data[best_symbol]['o']['avg_streak'],2), round(data[best_symbol]['e']['avg_streak'],2)
                time.sleep(5)
                if best_avg_o > 3.0 or best_avg_e > 3.0:
                    settings = {
                        "contract": "DIGITEVEN" if best_avg_e > best_avg_o else "DIGITODD",
                        "symbol": best_symbol
                    }
                    data = {
                        "message": f"Best streaks - {best_symbol}: O:{best_avg_o}, E:{best_avg_e}",
                        "settings": settings
                    }

                    # Send structured JSON
                    yield f"data: {json.dumps(data)}\n\n"
                else:
                    data = {
                        "message": f"Curr streaks - {best_symbol}: O:{best_avg_o}, E:{best_avg_e}"
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            except Exception as ex:
                data = {
                        "message": f"Error fetching streaks: {ex}",
                    }
                yield f"data: {data} \n\n"
                time.sleep(10)
    return Response(event_stream(), mimetype="text/event-stream")
if __name__ == '__main__':
    app.run(debug=True, port=8000, host="0.0.0.0")
