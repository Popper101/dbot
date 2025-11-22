import asyncio
import json
import websockets
import random
import requests 
from acad_random import Random
acad_random = Random()
API_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"
TOKENS = {"API_TOKEN_DEMO": "6aRpjKXBIQc51GC",
           "API_TOKEN":"tG1mz5HIRkWYvWw"
        }
def find_best_pattern(elements:list, pattern_size:int=3):
    patterns = {}
    block_size = pattern_size + 1  # pattern + outcome
    unique_elements = list(set(elements))
    for i in range(len(elements) - block_size + 1):
        pattern = tuple(elements[i:i + pattern_size])
        outcome = elements[i + pattern_size]
        pattern_dict = patterns.get(pattern, {k:0 for k in unique_elements})
        pattern_dict[outcome] += 1
        patterns[pattern] = pattern_dict
        
    
    # find the best matching pattern
    sorted_patterns = dict(sorted(patterns.items(), key=lambda item: max(item[1].values()), reverse=True))
    print(f"Identified patterns: {sorted_patterns}")
    # best pattern is the first one on the sorted patterns
    best_pattern = next(iter(sorted_patterns.items()), None)
    if best_pattern:
        return best_pattern[0], sorted_patterns[best_pattern[0]]
    return None, None
def find_best_pattern_entry(elements:list, pattern_size:int=3, outcome_size:int=10):
        patterns = {}
        block_size = pattern_size + outcome_size  # pattern + outcome
        unique_elements = list(set(elements))
        for i in range(len(elements) - block_size + 1):
            pattern = tuple(elements[i:i + pattern_size])
            outcome = elements[i + pattern_size: i + block_size]
            outcomes = {k: sum(1 for x in outcome if x == k) for k in unique_elements}
            pattern_dict = patterns.get(pattern, {k:0 for k in unique_elements})
            for k, v in outcomes.items():
                pattern_dict[k] += v
            patterns[pattern] = pattern_dict
            
        
        # find the best matching pattern
        sorted_patterns = dict(sorted(patterns.items(), key=lambda item: max(item[1].values()), reverse=True))
        print(f"Identified patterns: {sorted_patterns}")
        # best pattern is the first one on the sorted patterns
        best_pattern = next(iter(sorted_patterns.items()), None)
        if best_pattern:
            return best_pattern[0], sorted_patterns[best_pattern[0]]
        return None, None
class Bot:
    def __init__(self, base_stake:float, contract_type:str, symbol:str, barrier:int=None,
     tp:float=None, max_losses:int=None, martingale=None, curr_balance=None, stop_loss:float=None, user=None):
        self.user = user
        self.stop_loss = stop_loss
        self.stop_loss_initial = stop_loss
        self.base_stake = base_stake
        self.contract_type = contract_type
        self.barrier = barrier
        self.tp = tp
        self.pnl_hist = []
        self.trades = []
        self.stake = self.base_stake
        self.total_staked = 0
        self.is_complete = True
        self.running = False
        self.wins = 0
        self.losses = 0
        self.message = {}
        self.martingale = 1.2
        self.last_check = 0
        self.status = "Idle"
        self.max_losses = max_losses
        self.curr_balance = curr_balance
        self.__recoveries = 0
        self.martingale_levels = 7
        if martingale is not None:
            self.martingale = martingale
        elif contract_type is not None:
            if contract_type in ["DIGITDIFF"]:
                self.martingale = 12
            elif contract_type in ["DIGITOVER", "DIGITUNDER"]:
                if self.barrier:
                    if contract_type == "DIGITUNDER":
                        self.martingale = 1.3 ** (self.barrier/2)
                    else:
                        self.martingale = 1.3 ** ((10 - self.barrier)/2)
                self.martingale = 7 if self.martingale <=1 else self.martingale
            elif contract_type in ["DIGITEVEN", "DIGITODD"]:
                self.martingale = 2.1
    
    def update_result(self, trade_res):
        self.trades.append(trade_res)
        self.pnl_hist.append(trade_res["pnl"])
        self.total_staked += trade_res["stake"]
        self.wins += 1 if self.pnl_hist[-1] >0 else 0
        self.losses += 1 if self.pnl_hist[-1] <0 else 0
        # update stoploss
        if trade_res["pnl"] > 0:
            total_pnl = sum(self.pnl_hist)
            if total_pnl >0:
                # increase the stop loss by half of the profits. Think of it as pushing the line up closer to tp
                self.stop_loss = self.stop_loss_initial - total_pnl * 0.5 if self.stop_loss_initial is not None else None
            self.__recoveries = self.__recoveries -1 if self.__recoveries >0 else 0
        # else:
        #     self.__recoveries += 2

    def get_curr_loss_streak(self):
        if len(self.pnl_hist) == 0:
            return 0
        for x in range(len(self.pnl_hist)-1, -1, -1):
            if self.pnl_hist[x] > 0:
                return len(self.pnl_hist) -1 - x
        return len(self.pnl_hist)
    def get_stake(self, market_switch:bool=False):
        if len(self.pnl_hist) >0:
            expected = len(self.pnl_hist) * self.base_stake
            curr_stake = self.stake
            total_pnl = sum(self.pnl_hist)
            
            add = 0 if total_pnl <=0 else total_pnl * 0.005
            
            if len(self.pnl_hist) > self.last_check:
                
                if self.pnl_hist[-1] < 0 and self.get_curr_loss_streak() < self.martingale_levels:
                    self.stake *= self.martingale
                else:
                    self.stake = self.base_stake + add
                    if self.__recoveries > 0:
                        self.stake = curr_stake
                        # if self.__recoveries % 2 == 0:
                        #     self.stake /= self.martingale 
            # In case of market switch only adjust this if last result was a win
            if (self.contract_type in ["DIGITDIFF"] and not market_switch) or (self.contract_type in ["DIGITDIFF"] and market_switch and len(self.pnl_hist) > self.last_check and self.pnl_hist[-1] >0):
                self.stake = max(self.base_stake, (self.base_stake + total_pnl) * 0.1) # 10 % of total balance
            self.last_check = len(self.pnl_hist)
        
        return max(abs(round(self.stake,2)), 0.35)
    def should_recover(self):
        return sum(self.pnl_hist) < self.base_stake if self.tp is None else sum(self.pnl_hist) < self.tp
    def is_stop_loss_hit(self):
        is_hit = sum(self.pnl_hist) - self.stake < -self.stop_loss if self.stop_loss is not None else False
        if is_hit:
            self.message['error'] = f"Stop Loss hit {sum(self.pnl_hist):.2f}"
        return is_hit
    def swap_contract(self, contract_type):
        opposites = {
            "DIGITDIFF": "DIGITMATCH",
            "DIGITMATCH": "DIGITDIFF",
            "DIGITOVER": "DIGITUNDER",
            "DIGITUNDER": "DIGITOVER",
            "DIGITEVEN": "DIGITODD",
            "DIGITODD": "DIGITEVEN",
        }
        return opposites.get(contract_type, contract_type)

    
            
class DerivClient:
    def __init__(self, token=None):
        self.token = token
        self.ws = None
        self.is_authorized = False
        self.bot = Bot(1, "DIGITOVER", "None")

    async def connect(self):
        """Connect once and authorize."""
        if self.ws and self.ws.state == websockets.protocol.State.OPEN:
            print("^^^^^^ Already connected ^^^^^^")
            return  # Already connected

        self.ws = await websockets.connect(API_URL)
        await self.ws.send(json.dumps({"authorize": self.token}))
        response = json.loads(await self.ws.recv())
        

        if response.get("error"):
            raise Exception(f"Authorization failed: {response['error']['message']}")

        self.is_authorized = True
        print(f"✅ Authorized as {response['authorize']['loginid']}")

    async def ensure_connected(self):
        """Reconnect if the connection drops."""
        if not self.ws.state == websockets.protocol.State.OPEN:
            print("🔄 Reconnecting WebSocket...")
            self.is_authorized = False
            await self.connect()
    async def change_token(self, new_token):
        """
        Switch between demo/real tokens dynamically.
        Closes current WS, re-authorizes with new token.
        """
        if self.ws and self.ws.state == websockets.protocol.State.OPEN:
            await self.ws.close()
            print("🔒 Closed existing WebSocket connection.")

        self.token = new_token
        self.is_authorized = False
        print("🔁 Switching to new token...")

        await self.connect()  # reconnect + authorize
        print("✅ Token switched successfully.")

    async def keepalive(self, interval=30):
        """Send periodic ping to keep the connection alive."""
        curr_token = self.token
        while True:
            try:
                if self.ws and self.ws.state == websockets.protocol.State.OPEN:
                    await self.ws.send(json.dumps({"ping": 1}))
                    await asyncio.sleep(interval)
                    if self.token != curr_token:
                        print("🔁 Token change detected in keepalive.")
                        curr_token = self.token
                        await self.change_token(curr_token)
                else:
                    await self.ensure_connected()
            except Exception as e:
                print(f"⚠️ Keepalive error: {e}")
                await asyncio.sleep(5)
                await self.ensure_connected()

    async def buy(self,symbol="1HZ100V", ticks_to_trade=6, barrier=1, amount=1, contract_type="DIGITDIFF", user=None):
        """Send buy request using existing connection."""
        await self.ensure_connected()
        for count in range(ticks_to_trade):
            # Buy immediately without waiting for previous trade to finish
            if contract_type not in ["DIGITEVEN", "DIGITODD"]:
                await self.ws.send(json.dumps({
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
            if contract_type in ["DIGITEVEN", "DIGITODD"]:
                await self.ws.send(json.dumps({
                    "buy": 1,
                    "price": amount,
                    "parameters": {
                        "contract_type": contract_type,
                        "symbol": symbol,
                        "duration": 1,
                        "duration_unit": "t",
                        "basis": "stake",
                        "amount": amount,
                        "currency": "USD"
                    }
                }))

            if count >= ticks_to_trade:
                break
            await asyncio.sleep(1)
        return {"Bought":True, "Ticks": ticks_to_trade}

    def reverse_contract(self, contract_type):
        res = contract_type
        if contract_type == "DIGITEVEN": res = "DIGITODD"
        elif contract_type == "DIGITOVER": res = "DIGITUNDER"
        elif contract_type == "DIGITODD": res = "DIGITEVEN"
        elif contract_type == "DIGITUNDER": res = "DIGITOVER"
        return res

    async def buy_one(self, symbol="1HZ100V", barrier=1, amount=1, contract_type="DIGITDIFF", duration:int=1):
        """Use existing WebSocket to place a single buy."""
        try:
            await self.ensure_connected()

            # prepare buy payload
            payload = {
                "buy": 1,
                "price": amount,
                "parameters": {
                    "contract_type": contract_type,
                    "symbol": symbol,
                    "duration": duration,
                    "duration_unit": "t",
                    "basis": "stake",
                    "amount": amount,
                    "currency": "USD"
                },
                "subscribe": 1
            }
            if contract_type not in ["DIGITEVEN", "DIGITODD"]:
                payload["parameters"]["barrier"] = barrier

            # send buy
            await self.ws.send(json.dumps(payload))
            # wait for buy response
            self.bot.status = "Buying contract"
            # wait for buy response
            got_buy_response, count_remaining = False, 20
            msg = "Buying contract"
            
            while not got_buy_response and count_remaining >0:
                count_remaining -= 1
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                    msg = json.loads(response)
                    # ✅ Check for an error from Deriv
                    if msg.get("error"):
                        error_msg = msg["error"].get("message", "Unknown error")
                        message = f"❌ Buy failed: {error_msg}"
                        print(message)
                        self.bot.is_complete = True
                        self.bot.running = False
                        self.bot.message['error'] = message
                        return {"success": False, "error": error_msg}

                    # ✅ Confirm successful buy
                    if msg.get("msg_type") == "buy":
                        buy_data = msg.get("buy", {})
                        contract_id = buy_data.get("contract_id")
                        print(f"✅ Buy successful! Contract ID: {contract_id}")
                        self.bot.status = "Buying contract"
                        got_buy_response = True
                        subscription_id = msg.get("subscription", {}).get("id")
                        await(self.ws.send(json.dumps({ "forget": subscription_id })))
                    # print(f"message type: {msg.get('msg_type')}")
                        

                    
                except asyncio.TimeoutError:
                    print(f"Timeout waiting for response on trade {count_remaining+1}")
                    continue
                except Exception as e:
                    print(f"Error receiving response: {e}")
                    continue

            # extract trade info
            trade_result = {"raw": msg, "pnl": 0.0, "trade_result": {}}

            if "buy" in msg:
                buy_data = msg["buy"]
                # extract contract id or pnl if available
                trade = {"symbol": symbol,
                        "type": contract_type,
                        "stake": amount,
                        "pnl": float(buy_data.get("profit", 0.0) or buy_data.get("payout", 0.0)),
                        "result": buy_data.get("contract_id")
                }
                # wait for contract to finish
                await self.ws.send(json.dumps({
                    "proposal_open_contract": 1,
                    "contract_id": buy_data.get("contract_id"),
                    "subscribe":  1
                }))

                is_success, count_remaining = True, 20
                while True and count_remaining >0:
                    count_remaining -= 0
                    self.bot.status = "Waiting for result"
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=10)
                    data = json.loads(msg)
                    
                    if "proposal_open_contract" in data:
                        poc = data["proposal_open_contract"]
                        # Extract entry/exit details
                        entry_spot = poc.get("entry_tick")
                        exit_spot = poc.get("exit_tick")
                        pnl = poc.get("profit")  # or poc.get("profit_percentage")
                        stake = poc.get("buy_price")
                        curr_id = poc.get("contract_id")
                        # Once the contract ends, break
                        status = poc.get("status")
                        if poc.get("is_expired"):
                            print(f"✅ [{curr_id}]Contract ended | Entry: {entry_spot}, Exit: {exit_spot}, PnL: {pnl}, Status: {status}")
                            trade["pnl"] = pnl
                            trade["result"] = f"{entry_spot} \n{exit_spot}"
                            trade["stake"] = stake
                            trade["contract_id"] = curr_id
                            is_success = True
                            self.bot.status = "Contract settled"
                            self.bot.update_result(trade) # Add the trade to the container
                            await(self.ws.send(json.dumps({ "forget_all": "proposal_open_contract" })))
                            break
                        else:
                            if entry_spot is None or exit_spot is None:
                                print(f"[{curr_id}]Waiting | Status: {status}")
                                is_success = False
                        
                        
                        
                    await asyncio.sleep(1)
                # update bot results
            return msg
        except Exception as be:
            self.bot.message['error'] = f"Error occured in buy_one: {be}"
            return {"success": False, "error": str(be)}
    async def wait_signal(self, contract_type, deriv_ticks, symbol, max_ticks:int=20, pattern_size:int=None):
        pattern_size = 3 if pattern_size is None else pattern_size
        if deriv_ticks is not None:
            if contract_type in ["DIGITEVEN", "DIGITODD"]:
                last_digits = deriv_ticks.last_ticks.get(symbol, [])[-max_ticks:]
                ticks = ['E' if int(d) %2 == 0 else 'O' for d in last_digits]
                best_pattern, best_outcomes = find_best_pattern_entry(ticks, pattern_size=pattern_size)
                best_outcome = max(best_outcomes.items(), key=lambda x: x[1])
                if best_outcome[0] == 'E':
                    contract_type = "DIGITEVEN"
                else:
                    contract_type = "DIGITODD"
                self.bot.message['pattern'] = f"{contract_type}@{best_outcome[1]}/{sum(best_outcomes.values())} based on pattern {best_pattern}"
                best_pattern = list(best_pattern)
                while deriv_ticks is not None and not self.bot.is_complete:
                    # fetch latest digit from deriv ticks
                    last_digits = deriv_ticks.last_ticks.get(symbol, [])
                    if len(last_digits) >0:
                        last_3 = last_digits[-pattern_size:]
                        last_3 = ['E' if int(d) %2 ==0 else 'O' for d in last_3]
                        if last_3 == best_pattern:
                            self.bot.message['info'] = f"Switched to {contract_type} on {last_3}, {symbol}"
                            break
                        
                        else:
                            self.bot.message['info'] = f"Last digits: {last_3} waiting for signal"
                    await asyncio.sleep(1)
            elif contract_type in ["DIGITOVER", "DIGITUNDER"]:
                last_digits = deriv_ticks.last_ticks.get(symbol, [])[-max_ticks:]
                ticks = ['O' if int(d) > self.bot.barrier else 'U' if int(d) < self.bot.barrier else 'E' for d in last_digits]
                best_pattern, best_outcomes = find_best_pattern_entry(ticks, pattern_size=pattern_size)
                best_outcome = max(best_outcomes.items(), key=lambda x: x[1])
                if best_outcome[0] == 'O':
                    contract_type = "DIGITOVER"
                else:
                    contract_type = "DIGITUNDER"
                self.bot.message['pattern'] = f"{contract_type}@{best_outcome[1]}/{sum(best_outcomes.values())} based on pattern {best_pattern}"
                best_pattern = list(best_pattern)
                while deriv_ticks is not None and not self.bot.is_complete:
                    # fetch latest digit from deriv ticks
                    last_digits = deriv_ticks.last_ticks.get(symbol, [])
                    if len(last_digits) >0:
                        last_3 = last_digits[-pattern_size:]
                        last_3 = ['O' if int(d) > self.bot.barrier else 'U' if int(d) < self.bot.barrier else 'E' for d in last_3]
                        if last_3 == best_pattern:
                            self.bot.message['info'] = f"Switched to {contract_type} on {last_3}, {symbol}"
                            break
                        
                        else:
                            self.bot.message['info'] = f"Last digits: {last_3} waiting for signal"
                    await asyncio.sleep(1)
    async def buy_bot_strategy(self, symbol="1HZ100V", ticks_to_trade=6, barrier=1, amount=1, contract_type="DIGITDIFF", tp=None, max_losses=None, martingale=None, 
    duration:int=1, market_switch:bool=True, stop_loss:float=None, contract_switch:bool=False, user=None, deriv_ticks=None, reverse_wait:int=2, strategy=None):
        """Use existing WebSocket to place sequential buys via the Bot instance."""
        try:
            await self.ensure_connected()

            # initialize the bot instance once
            self.bot = Bot(
                base_stake=amount,
                contract_type=contract_type,
                symbol=symbol,
                barrier=barrier,
                tp=tp,
                max_losses=max_losses,
                martingale=martingale,
                stop_loss=stop_loss,
                user=user
            )
            self.bot.is_complete = False
            self.bot.is_running = True
            count = -1
            curr_loss_streak = 0
            if strategy and strategy == "random":
                contract_swap_interval = max_losses if max_losses else 2
                contracts = [contract_type, self.reverse_contract(contract_type)]
                curr_contract = acad_random.choice(contracts)
                while self.bot.should_recover() and not self.bot.is_complete and not self.bot.is_stop_loss_hit():
                    self.bot.running = True
                    count += 1
                    print("pnl:" , self.bot.pnl_hist)
                    # wait for entry point
                    amount = self.bot.get_stake(market_switch=market_switch)
                    await self.buy_one(symbol=symbol, contract_type=curr_contract, barrier=barrier, amount=amount, duration=duration)
                    print(f"Last Trade: {self.bot.trades[-1]}")
                    if self.bot.pnl_hist[-1] <0:
                        curr_loss_streak += 1
                        if curr_loss_streak % contract_swap_interval == 0:
                            # reverse list
                            contracts = list(reversed(contracts))
                            contract_swap_interval = (contract_swap_interval + 1) % 4 +1
                    else:
                        curr_loss_streak = 0 # reset
                    # switch contract randomly
                    curr_contract = acad_random.choice(contracts)
                    # wait briefly before next trade
                    await asyncio.sleep(0.2)
            else:
                # even odd confirmation
                
                # await self.wait_signal(contract_type, deriv_ticks, symbol, user.max_ticks, pattern_size=reverse_wait)
                while self.bot.should_recover() and not self.bot.is_complete and not self.bot.is_stop_loss_hit():
                    self.bot.running = True
                    count += 1
                    print("pnl:" , self.bot.pnl_hist)
                    # wait for entry point
                    if max_losses and curr_loss_streak > 0 and curr_loss_streak % max_losses == 0:
                        await self.wait_signal(contract_type, deriv_ticks, symbol, user.max_ticks, pattern_size=reverse_wait)
                    amount = self.bot.get_stake(market_switch=market_switch)
                    await self.buy_one(symbol=symbol, contract_type=contract_type, barrier=barrier, amount=amount, duration=duration)
                    print(f"Last Trade: {self.bot.trades[-1]}")
                    if self.bot.pnl_hist[-1] <0: # on loss
                        curr_loss_streak += 1
                        # change contract type to even odd to recover
                        if market_switch is True and contract_type in ["DIGITMATCH", "DIGITDIFF"]:
                            contract_type = "DIGITODD" if random.randint(1,9) %2 ==0 else "DIGITEVEN"
                            self.bot.message['info'] = f"Current loss streak: {curr_loss_streak +1}, changing contract"
                        elif contract_type in ["DIGITMATCH", "DIGITDIFF"] and self.bot.max_losses % curr_loss_streak == 0:
                            symbol, digit = self.fetch_best_matchersdiffers(contract_type)
                            barrier = digit if digit is not None else barrier
                            self.bot.message['info'] = f"Symbol and digit changed {symbol}: {barrier}"
                        if contract_type in ["DIGITEVEN", "DIGITODD"]:
                            # check once alafu anguka nayo
                            if contract_switch is True:
                                if self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                                    contract_type = self.reverse_contract(contract_type)
                                    self.bot.message['info'] =f"Contract changed to [{contract_type}]:{symbol}"
                            if market_switch is True and self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak == self.bot.max_losses:
                                self.bot.message['info'] = f"Max loss streak reached, switching contract"
                                symbol, contract_type, streak = self.fetch_best_digit(contract_type)
                                # contract_type = self.reverse_contract(contract_type)
                                self.bot.message['info'] =f"Symbol changed to [{contract_type}]:{symbol}@ {streak}"
                            elif self.bot.max_losses is not None and curr_loss_streak > self.bot.max_losses and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                                contract_type, pct = self.fetch_best_streak(symbol)
                                await self.wait_signal(contract_type, deriv_ticks, symbol, user.max_ticks, pattern_size=reverse_wait)
                                # choices = [contract_type, self.reverse_contract(contract_type)]
                                # contract_type1 = random.choice(list(reversed(choices)))
                                # pct = 100-pct if contract_type1 != contract_type else pct
                                # contract_type = contract_type1
                                self.bot.message['info'] =f"Contract changed to [{contract_type}]:{symbol}@{pct:.2f}"
                        if contract_switch is True and contract_type in ["DIGITOVER", "DIGITUNDER"]:
                            if self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                                # symbol, contract_type, pct, barrier = self.fetch_best_digit(contract_type, barrier=barrier)
                                contract_type = self.reverse_contract(contract_type)
                                barrier = 9- barrier # swap barrier
                                self.bot.message['info'] =f"Changed to [{contract_type}] {symbol}:{barrier}"
                        elif market_switch is True and contract_type in ["DIGITOVER", "DIGITUNDER"]:
                            if self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                                symbol, contract_type, pct, barrier = self.fetch_best_digit(contract_type, barrier=barrier)
                                # contract_type = self.reverse_contract(contract_type)
                                self.bot.message['info'] =f"Changed to [{contract_type}] {symbol}:{barrier}@{pct:.2f}"

                        
                    else:
                        curr_loss_streak = 0 # reset
                        if contract_type in ["DIGITEVEN", "DIGITODD"] and self.bot.contract_type in ["DIGITMATCH", "DIGITDIFF"]:
                            contract_type = self.bot.contract_type
                        if contract_type in ["DIGITMATCH", "DIGITDIFF"]:
                            if curr_loss_streak == 0:
                                symbol, digit = self.fetch_best_matchersdiffers(contract_type)
                                barrier = digit if digit is not None else barrier
                                self.bot.message['info'] = f"Symbol and digit changed {symbol}: {barrier}"
                        
                    # wait briefly before next trade
                    await asyncio.sleep(0.2)
                
            # set status to complete
            self.bot.status = "Idle"
            self.bot.is_complete = True
            self.bot.is_running = False
        except Exception as be:
            self.bot.message['error'] = f"Error occured buying: {be}"
        finally:
            await self.close()
    
    async def buy_bot(self, symbol="1HZ100V", ticks_to_trade=6, barrier=1, amount=1, contract_type="DIGITDIFF", tp=None, max_losses=None, martingale=None, 
    duration:int=1, market_switch:bool=True, stop_loss:float=None, contract_switch:bool=False, user=None, deriv_ticks=None):
        """Use existing WebSocket to place sequential buys via the Bot instance."""
        try:
            await self.ensure_connected()

            # initialize the bot instance once
            self.bot = Bot(
                base_stake=amount,
                contract_type=contract_type,
                symbol=symbol,
                barrier=barrier,
                tp=tp,
                max_losses=max_losses,
                martingale=martingale,
                stop_loss=stop_loss,
                user=user
            )
            self.bot.is_complete = False
            self.bot.is_running = True
            count = -1
            curr_loss_streak = 0
            if contract_type in ["DIGITOVER", "DIGITUNDER"] and market_switch is True:
                pattern = self.fetch_pattern(symbol)
                if pattern is not None:
                    print(f"⭐ Using pattern: {pattern}")
                    contract_type = 'DIGITOVER' if pattern['trade'] == 'o' else 'DIGITUNDER'
                    symbol = pattern['symbol']
                    barrier = pattern['barrier']
            while self.bot.should_recover() and not self.bot.is_complete and not self.bot.is_stop_loss_hit():
                if pattern and market_switch is True and deriv_ticks is not None and contract_type in ["DIGITOVER", "DIGITUNDER"]:
                    # fetch latest digit from deriv ticks
                    last_digits = deriv_ticks.last_ticks.get(symbol, [])
                    if len(last_digits) >0:
                        last_3 = last_digits[-3:]
                        last_3 = ['o' if int(d) > barrier else 'u' if int(d)< barrier else 'e' for d in last_3]
                        if last_3 == ['o','o','u'] and pattern['contract'] == 'u':
                            # contract_type = "DIGITUNDER"
                            self.bot.message['info'] = f"Switched to {contract_type} on {last_3}, {symbol}, barrier {barrier}"
                            
                        elif last_3 == ['u','u','o'] and pattern['contract'] == 'o':
                            # contract_type = "DIGITOVER"
                            self.bot.message['info'] = f"Switched to {contract_type} on {last_3}, {symbol}, barrier {barrier}"
                        else:
                            self.bot.message['info'] = f"Last digits: {last_3} waiting for signal"
                            continue # always wait for signal
                self.bot.running = True
                count += 1
                print("pnl:" , self.bot.pnl_hist)
                # get stake from bot logic
                stake = self.bot.get_stake()

                # prepare buy payload
                payload = {
                    "buy": 1,
                    "price": stake,
                    "parameters": {
                        "contract_type": contract_type,
                        "symbol": symbol,
                        "duration": duration,
                        "duration_unit": "t",
                        "basis": "stake",
                        "amount": stake,
                        "currency": "USD"
                    },
                    "subscribe": 1
                }
                if contract_type not in ["DIGITEVEN", "DIGITODD"]:
                    payload["parameters"]["barrier"] = barrier
                await self.ensure_connected() # ensure authorized before proceeding
                # send buy
                await self.ws.send(json.dumps(payload))
                self.bot.status = "Buying contract"
                # wait for buy response
                got_buy_response, count_remaining = False, 20
                msg = "Buying contract"
                
                while not got_buy_response and count_remaining >0:
                    count_remaining -= 1
                    try:
                        response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                        msg = json.loads(response)
                        # ✅ Check for an error from Deriv
                        if msg.get("error"):
                            error_msg = msg["error"].get("message", "Unknown error")
                            message = f"❌ Buy failed: {error_msg}"
                            print(message)
                            self.bot.is_complete = True
                            self.bot.running = False
                            self.bot.message['error'] = message
                            return {"success": False, "error": error_msg}

                        # ✅ Confirm successful buy
                        if msg.get("msg_type") == "buy":
                            buy_data = msg.get("buy", {})
                            contract_id = buy_data.get("contract_id")
                            print(f"✅ Buy successful! Contract ID: {contract_id}")
                            self.bot.status = "Buying contract"
                            got_buy_response = True
                            subscription_id = msg.get("subscription", {}).get("id")
                            await(self.ws.send(json.dumps({ "forget": subscription_id })))
                        # print(f"message type: {msg.get('msg_type')}")
                            

                        
                    except asyncio.TimeoutError:
                        print(f"Timeout waiting for response on trade {count+1}")
                        continue
                    except Exception as e:
                        print(f"Error receiving response: {e}")
                        continue

                # extract trade info
                trade_result = {"raw": msg, "pnl": 0.0, "trade_result": {}}

                if "buy" in msg:
                    buy_data = msg["buy"]
                    # extract contract id or pnl if available
                    trade = {"symbol": symbol,
                            "type": contract_type,
                            "stake": stake,
                            "pnl": float(buy_data.get("profit", 0.0) or buy_data.get("payout", 0.0)),
                            "result": buy_data.get("contract_id")
                    }
                    # wait for contract to finish
                    await self.ws.send(json.dumps({
                        "proposal_open_contract": 1,
                        "contract_id": buy_data.get("contract_id"),
                        "subscribe":  1
                    }))

                    is_success, count_remaining = True, 20
                    while True and count_remaining >0:
                        count_remaining -= 0
                        self.bot.status = "Waiting for result"
                        msg = await asyncio.wait_for(self.ws.recv(), timeout=10)
                        data = json.loads(msg)
                        
                        if "proposal_open_contract" in data:
                            poc = data["proposal_open_contract"]
                            # Extract entry/exit details
                            entry_spot = poc.get("entry_tick")
                            exit_spot = poc.get("exit_tick")
                            pnl = poc.get("profit")  # or poc.get("profit_percentage")
                            stake = poc.get("buy_price")
                            curr_id = poc.get("contract_id")
                            # Once the contract ends, break
                            status = poc.get("status")
                            if poc.get("is_expired"):
                                print(f"✅ [{curr_id}]Contract ended | Entry: {entry_spot}, Exit: {exit_spot}, PnL: {pnl}, Status: {status}")
                                trade["pnl"] = pnl
                                trade["result"] = f"{entry_spot} \n{exit_spot}"
                                trade["stake"] = stake
                                trade["contract_id"] = curr_id
                                is_success = True
                                self.bot.status = "Contract settled"
                                self.bot.update_result(trade) # Add the trade to the container
                                await(self.ws.send(json.dumps({ "forget_all": "proposal_open_contract" })))
                                curr_loss_streak += 1 if trade["pnl"] < 0 else -curr_loss_streak
                                break
                            else:
                                if entry_spot is None or exit_spot is None:
                                    print(f"[{curr_id}]Waiting | Status: {status}")
                                    is_success = False
                            
                            
                            
                        await asyncio.sleep(1)
                    # update bot results
                    
                    
                    print(f"Last Trade: {self.bot.trades[-1]}")
                if contract_type in ["DIGITMATCH", "DIGITDIFF"]:
                    if market_switch is True:
                        if self.bot.max_losses is not None and curr_loss_streak> 0 and curr_loss_streak % self.bot.max_losses == 0:
                            symbol, digit = self.fetch_best_matchersdiffers(contract_type)
                            barrier = digit if digit is not None else barrier
                            self.bot.message['info'] = f"Symbol and digit changed {symbol}: {barrier}"
                        if curr_loss_streak == 0:
                            symbol, digit = self.fetch_best_matchersdiffers(contract_type)
                            barrier = digit if digit is not None else barrier
                            self.bot.message['info'] = f"Symbol and digit changed {symbol}: {barrier}"
                elif contract_type in ["DIGITEVEN", "DIGITODD"]:
                    if market_switch is True and self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                        pct = 0
                        countdown = 10
                        while pct < 70 and countdown >=0:
                            countdown -=1
                            if countdown !=9:
                                contract_type = self.bot.swap_contract(contract_type)
                            symbol, contract_type, pct = self.fetch_best_digit(contract_type)
                            # contract_type = self.reverse_contract(contract_type)
                            self.bot.message['info'] =f"Symbol changed to [{contract_type}]:{symbol}@{pct:.2f}"
                    elif contract_switch is True and self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                        contract_type, pct = self.fetch_best_streak(symbol)
                        self.bot.message['info'] =f"Contract changed to [{contract_type}]:{symbol}@{pct}"
                            
                elif market_switch is True and contract_type in ["DIGITOVER", "DIGITUNDER"]:
                    if market_switch is True and self.bot.max_losses is not None and curr_loss_streak >0 and curr_loss_streak % self.bot.max_losses == 0:
                        symbol, contract_type, pct, barrier = self.fetch_best_digit(contract_type, barrier=barrier)
                        self.bot.message['info'] =f"Changed to [{contract_type}] {symbol}:{barrier}@{pct:.2f}"
                    elif curr_loss_streak > 0 and curr_loss_streak % self.bot.max_losses == 0:
                        pattern = self.fetch_pattern(symbol)
                        print(f"⭐ Using pattern: {pattern}")
                        contract_type = 'DIGITOVER' if pattern['trade'] == 'o' else 'DIGITUNDER'
                        symbol = pattern['symbol']
                        barrier = pattern['barrier']
                elif self.bot.max_losses is not None and curr_loss_streak > 0 and curr_loss_streak % self.bot.max_losses == 0:
                    if market_switch is True:
                        # self.bot.pnl_hist.append(0)
                        # if random.randint(1, 9) % 2 == 0:
                        #     self.bot.message['info'] = "Max streak reached, "
                        contract_type = self.reverse_contract(contract_type)
                
                # if curr_loss_streak > 1:
                #     duration = (duration +1) % 3 +1 # 1 to 2 all the time
                # wait briefly before next trade
                await asyncio.sleep(0.2)
            self.bot.status = "Idle"
            self.bot.is_complete = True
            self.bot.running = False
            
            # return summary
            return {
                "Bought": True,
                "TotalTrades": len(self.bot.trades),
                "TotalPnL": round(sum(self.bot.pnl_hist), 2),
                "TradeHistory": self.bot.trades
            }
        except Exception as be:
            self.bot.message['error'] = f"Error occured buying: {be}"
            return {"success": False, "error": self.bot.message['error']}
        finally:
            await self.close()

    def fetch_best_matchersdiffers(self, contract_type:str):
        response = requests.post("http://localhost:8000/fetch-best-symbol", json={"contract_type":contract_type})
        digit = response.json().get("digit", None)
        symbol = response.json().get("symbol")
        return symbol, digit
    def fetch_best_digit(self, contract_type:str, barrier=None):
        
        response = requests.post("http://localhost:8000/fetch-best-symbol", json={"contract_type":contract_type, "barrier":barrier})
        contract_type = response.json().get("contract_type", None)
        symbol = response.json().get("symbol")
        pct = response.json().get("pct")
        if barrier is None:
            return symbol, contract_type, pct
        barrier = response.json().get("digit")
        return symbol, contract_type, float(pct), barrier
    def fetch_best_streak(self, symbol:str):
        response = requests.get("http://localhost:8000/stats/streak?type=json")
        data = response.json().get(symbol)
        best = max(data.items(), key=lambda x: x[1]['avg_streak'])
        contracts = {"e":"DIGITEVEN", "o": "DIGITODD"}
        best_contract = contracts.get(best[0], "Invalid")
        streak = best[1]['avg_streak']
        return best_contract, streak
    def fetch_pattern(self, symbol:str):
        url = "http://localhost:5000/best_all"
        data = requests.get(url).json()
        filter_barriers = [4,5]
        filter_symbols = ["1HZ15V", "1HZ30V", "1HZ90V"]
        data1 = [d for d in data if d['barrier'] in filter_barriers and d['symbol'] not in filter_symbols]
        data = data1 if len(data1)> 0 else [d for d in data if d['symbol'] not in filter_symbols]
        best = data[0] # default sorted by highest pct
        return best
    async def close(self):
        """Close the connection gracefully."""
        if self.ws and self.ws.state == websockets.protocol.State.OPEN:
            await self.ws.close()
            print("🔌 Connection closed.")

class DerivTicks:
    def __init__(self, symbols, max_ticks=1000, token=None):
        self.token = token
        self.symbols = symbols
        self.last_ticks = {s: [] for s in symbols}
        self.ws = None
        self.is_authorized = False
        self.max_ticks = max_ticks

    async def connect(self):
        """(Re)connect and authorize."""
        if self.ws:
            await self.ws.close()

        self.ws = await websockets.connect(API_URL, ping_interval=None)  
        # disable built-in ping — we’ll do our own
        await self.ws.send(json.dumps({"authorize": self.token}))
        response = json.loads(await self.ws.recv())
        print("✅ Authorized as", response["authorize"]["loginid"])
        self.is_authorized = True

    async def subscribe_all(self):
        """Subscribe to all tick streams and keep them alive."""
        await self.connect()
        for symbol in self.symbols:
            await self.ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
            print(f"📡 Subscribed to {symbol}")

        # Run two concurrent tasks:
        receiver = asyncio.create_task(self._receive_ticks())
        pinger = asyncio.create_task(self._keep_alive())

        await asyncio.gather(receiver, pinger)

    async def _keep_alive(self):
        """Send a ping every 15 seconds to prevent timeout."""
        while True:
            try:
                if self.ws:
                    await self.ws.send(json.dumps({"ping": 1}))
                await asyncio.sleep(15)
            except Exception as e:
                print("⚠️ Ping failed, reconnecting:", e)
                await asyncio.sleep(3)
                await self.connect()

    async def _receive_ticks(self):
        """Continuously receive ticks with timeout + auto-reconnect."""
        while True:
            try:
                msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=15))

                if msg.get("msg_type") == "tick":
                    symbol = msg["tick"]["symbol"]
                    quote = msg["tick"]["quote"]
                    decimals = msg["tick"]["pip_size"]
                    formatted = f"{quote:.{decimals}f}"
                    self.last_ticks[symbol].append(formatted[-1])

                    # keep memory bounded
                    if len(self.last_ticks[symbol]) > self.max_ticks:
                        self.last_ticks[symbol].pop(0)

            except asyncio.TimeoutError:
                print("⏳ Timeout – sending ping manually to keep alive")
                await self.ws.send(json.dumps({"ping": 1}))
            except websockets.ConnectionClosed:
                print("🔄 Connection closed – reconnecting...")
                await self.connect()
                for symbol in self.symbols:
                    await self.ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
                    print(f"📡 Re-subscribed to {symbol}")
            except Exception as e:
                print("❌ Error receiving ticks:", e)
                await asyncio.sleep(3)
                await self.connect()

# Example test
async def main():
    client = DerivClient(TOKENS["API_TOKEN_DEMO"])
    await client.connect()
    asyncio.create_task(client.keepalive())  # keep alive in background

    response = await client.buy_one(symbol="1HZ75V", contract_type="DIGITUNDER", barrier=5, amount=1)
    print("📦 Buy response:", response)

    await asyncio.sleep(10)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
    # Create DerivTicks instance
    # volatilities = [10,25,50, 75, 100]
    # SYMBOLS = [f"1HZ{x}V" for x in volatilities] + [f'R_{x}' for x in volatilities]
    # ticks_client = DerivTicks(SYMBOLS)
    # asyncio.run(ticks_client.subscribe_all())
