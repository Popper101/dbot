import requests
import json
import numpy as np
data = []
patterns = ['oou', 'uuo', 'ouou', 'uouo', 'uuou', 'oouo', 'uuoo', 'oouu','ooou','uuuo']
def to_pattern(data:list, barrier:int):
    res = ['o' if x > barrier else 'u' if x < barrier else 'e' for x in data]
    return ''.join(res)
def to_outcome(x:int, barrier:int):
    return 'o' if x > barrier else 'u' if x < barrier else 'e'

def check_res(pattern, data:list):
    global patterns
    pattern_len = len(pattern)

    block = pattern_len +1
    barriers = [x for x in range(1,9)]
    # store barriers, patterns, count as values
    outcomes = {}
    results = {}
    for x in range(0, len(data), block):
        curr_ticks = data[x:x+pattern_len]
        for  barrier in barriers:
            curr_pattern = to_pattern(curr_ticks, barrier)
            if curr_pattern == pattern:
                outcomes[barrier] = outcomes.get(barrier, {curr_pattern:0})
                outcomes[barrier][curr_pattern] = outcomes[barrier].get(curr_pattern, 0) +1
                res = data[x+pattern_len] # the result
                res = to_outcome(res, barrier)
                # add the reults
                key = f'{(barrier, curr_pattern)}'
                existing = results.get(key, {'result':{}})
                existing['result'][res] = existing['result'].get(res, 0) + 1
                results[key] = existing

    sorted_outcomes = dict(sorted(outcomes.items(), key=lambda x: sum(x[1].values()), reverse=True))
    sorted_results = dict(
    sorted(
            results.items(),
            key=lambda item: list(item[1]['result'].values())[0],
            reverse=True
        )
    )

    return sorted_outcomes, sorted_results
def summarize(data:dict):
    symbol = list(data)[0]
    datas = data[symbol]
    summary = set()
    for d in datas:
        barriers = list(d) # the barriers
        for b in barriers:
            patterns = list(d[b])
            for p in patterns:
                value= d[b][p]
                s = f"{symbol}, {b}, {p}: {value}"
                summary.add(s)
    return summary
def run():
    global patterns, data
    url = "http://localhost:8000/last_ticks"
    res = requests.get(url)
    data = res.json()
    symbols = list(data.keys())
    all_outcomes = {}
    for symbol in symbols:
        curr_data = data[symbol]
        best_outcomes = []
        for pattern in patterns:
            outcomes, results = check_res(pattern, curr_data)
            # print(results)
            # add to best outcomes
            added_count = 0
            for key, value in results.items():
                if max(value['result'].values()) < 2: break
                best_outcomes.append({key:value})
                added_count +=1
                if added_count >2:
                    break
        # sort the best_outcomes
        sorted_outcomes = sorted(
            best_outcomes,
            key=lambda d: max(list(d.values())[0]['result'].values()),
            reverse=True
        )

        all_outcomes[symbol] = sorted_outcomes[:3]
    # Sort for better view
    for symbol, outcomes in all_outcomes.items():
        # Each item is like {"(2, 'oou')": {"result": {"o": 2, "u": 1}}}
        outcomes.sort(
            key=lambda x: max((list(x.values())[0]['result'].values()) or [0]),
            reverse=True
        )

    # Print formatted
    print("-" * 50)
    print(json.dumps({str(k): v for k, v in all_outcomes.items()}, indent=4))

    return all_outcomes



import numpy as np
from math import log, exp

def prob_within_x_ensemble(last_digits, target_digit, x=6,
                           val_window=40, alpha=1e-3, ewma_lambda=0.2):
    """
    Ensemble estimate for P(target_digit appears within next x ticks).
    last_digits: list-like of ints 0..9 (oldest -> latest), latest at last element
    target_digit: int 0..9
    x: lookahead ticks
    val_window: how many of the most recent transitions to use for weighting models
    alpha: small Laplace-like smoothing for counts
    ewma_lambda: decay factor for EWMA (higher -> recent ticks weigh more)
    
    Returns: dict {
       'ensemble_prob': float,
       'model_probs': {'freq':..., 'markov':..., 'ewma':...},
       'weights': {'freq':..., 'markov':..., 'ewma':...}
    }
    """
    digits = list(last_digits)
    n_total = len(digits)
    if n_total < 2:
        raise ValueError("Need at least 2 ticks to build transition info.")
    n_classes = 10
    # ----- helper: empirical frequency probability (single-tick) -----
    def empirical_p(history):
        counts = np.zeros(n_classes)
        for d in history:
            counts[d] += 1
        probs = (counts + alpha) / (counts.sum() + alpha * n_classes)
        return probs  # vector size 10

    # ----- helper: 1-step Markov transition matrix -----
    def build_markov(history):
        T = np.zeros((n_classes, n_classes))
        for a, b in zip(history[:-1], history[1:]):
            T[a, b] += 1
        # smoothing
        T = T + alpha
        row_sums = T.sum(axis=1, keepdims=True)
        # if a row sum is zero (unseen state), make it uniform
        row_sums[row_sums == 0] = n_classes * alpha
        T = T / row_sums
        return T

    # ----- helper: EWMA single-tick distribution -----
    def ewma_p(history, lam):
        # weight most recent more: iterate from last backward
        w_sum = 0.0
        counts = np.zeros(n_classes)
        cur_w = 1.0
        for d in reversed(history):
            counts[d] += cur_w
            w_sum += cur_w
            cur_w *= (1 - lam)
        probs = (counts + alpha) / (w_sum + alpha * n_classes)
        return probs

    # ----- compute single-tick predictive probabilities for each model -----
    freq_probs = empirical_p(digits)           # P(next tick digit = j) ignoring state
    T = build_markov(digits)                   # transition matrix from whole history
    current = digits[-1]
    # Markov one-step distribution given current state:
    markov_one = T[current]                    # row vector length 10
    ewma_probs = ewma_p(digits, ewma_lambda)

    # ----- compute "prob within x" from each model -----
    # freq model: assume independence
    p_freq_single = freq_probs[target_digit]
    p_freq_within_x = 1 - (1 - p_freq_single) ** x

    # markov model: iterate x steps starting from current state
    v = np.zeros(n_classes); v[current] = 1.0
    p_seen_markov = 0.0
    for _ in range(x):
        v = v @ T
        p = v[target_digit]
        p_seen_markov += (1 - p_seen_markov) * p

    # ewma model: treat like iid with p from ewma
    p_ewma_single = ewma_probs[target_digit]
    p_ewma_within_x = 1 - (1 - p_ewma_single) ** x

    model_probs = {
        'freq': float(p_freq_within_x),
        'markov': float(p_seen_markov),
        'ewma': float(p_ewma_within_x)
    }

    # ----- compute performance-based weights using recent validation transitions -----
    # We'll compute summed log-likelihood of each model on last `val_window` one-step predictions.
    # For t from (start) .. (n_total-2): build model on history[:t+1] and score prediction of history[t+1].
    ll_freq = ll_markov = ll_ewma = 0.0
    # ensure val_window fits
    max_possible = n_total - 1
    vw = min(val_window, max_possible)
    start_idx = n_total - 1 - vw  # earliest index t where we predict t+1
    # safety: if vw small, still proceed
    for t in range(start_idx, n_total - 1):
        hist = digits[:t+1]   # data available up to t (inclusive)
        actual = digits[t+1]
        # freq from hist
        fp = empirical_p(hist)[actual]
        # markov from hist
        Tt = build_markov(hist)
        cur = hist[-1]
        mp = Tt[cur, actual]
        # ewma from hist
        ep = ewma_p(hist, ewma_lambda)[actual]
        # numeric stability: clamp
        fp = max(fp, 1e-12); mp = max(mp, 1e-12); ep = max(ep, 1e-12)
        ll_freq += log(fp)
        ll_markov += log(mp)
        ll_ewma += log(ep)

    # softmax-like weights from log-likelihoods
    # subtract max for stability
    lls = np.array([ll_freq, ll_markov, ll_ewma])
    max_ll = lls.max()
    exps = np.exp(lls - max_ll)
    weights = exps / exps.sum()
    w_freq, w_markov, w_ewma = weights.tolist()

    # final ensemble probability: weighted average of model "within-x" probs
    ensemble_prob = w_freq * p_freq_within_x + w_markov * p_seen_markov + w_ewma * p_ewma_within_x

    return {
        'ensemble_prob': round(float(ensemble_prob), 4),
        'model_probs': {k: round(v, 4) for k, v in model_probs.items()},
        'weights': {'freq': round(w_freq, 4), 'markov': round(w_markov, 4), 'ewma': round(w_ewma, 4)},
        'meta': {'n_ticks': n_total, 'val_window_used': vw}
    }

def calculator():
    return_pct = 0.09
    balance = 10
    results = [1,1,0,1,1,1,1,1,1,0]
    accumulator, accumulator_initial = 0.3, 0.3
    for r in results:
        stake = round(balance * accumulator, 2)
        print(f"Stake: {stake} @ {accumulator}", end=" ")
        res = round(stake * return_pct,2) if r ==1 else -stake
        balance += res
        print(f"Balance: {balance:,.2f}")
        if r == 0:
            accumulator *=2.5
        else:
            accumulator = max(round(accumulator* .8,2), accumulator_initial)

if __name__ == "__main__":
    # run()
    # test
    calculator()
