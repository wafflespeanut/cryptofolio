import functools
import json
from flask import Flask, request

from .exchange import Client
from .storage import Storage


app = Flask(__name__)
store: Storage = None
spot: Client = None
secret = None


def create_app(client: Client, storage: Storage, code: str):
    global spot, app, store, secret
    spot = client
    store = storage
    secret = code
    return app


def jsonify(data, code=200):
    return app.response_class(
        response=json.dumps(data),
        status=code,
        mimetype="application/json",
    )


def needs_code(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if request.args.get("code") != secret:
            return jsonify({"msg": "Invalid auth"}, code=401)
        return f(*args, **kwargs)
    return wrapped


@app.route('/tickers', methods=['GET'])
@needs_code
def tickers():
    return jsonify({
        "tickers": spot.tickers(),
        "distribution": store.load_distribution(),
    })


@app.route('/purchases', methods=['GET'])
@needs_code
def purchases():
    is_mock = request.args.get("mock") is not None
    purchases = store.list_purchases(mock=is_mock)
    return jsonify(purchases)


@app.route('/balances', methods=['GET'])
@needs_code
def balances():
    tickers = spot.tickers()
    balances = {}
    total = 0
    for sym, qty in spot.balances().items():
        price = 1 if sym in ("USDT", "USD") else tickers[sym][0]
        balances.setdefault(sym, [0, 0])
        total += price * float(qty)
        balances[sym][0] += price * float(qty)
    for sym in list(balances.keys()):
        balances[sym][1] = (balances[sym][0] * 100) / total
    return jsonify(balances)


@app.route('/buy', methods=['POST'])
@needs_code
def buy():
    amount = request.args.get("amount")
    try:
        amount = float(amount)
    except Exception:
        return jsonify({"msg": "Invalid amount"}, code=400)

    is_mock = request.args.get("mock") is not None
    replace_dist = request.args.get("replace") is not None

    distribution = request.json
    if round(sum(v for v in distribution.values()), 2) != 100:
        return jsonify({"msg": "Sum is not 100%"}, code=400)
    tickers = spot.tickers()
    for asset, fraction in distribution.items():
        if tickers.get(asset) is None:
            return jsonify({"msg": f"{asset} missing in exchange"}, code=400)
        price = tickers[asset][0]
        funds = amount * fraction * 0.01
        if funds < 1:
            return jsonify({"msg": f"Amount for {asset} too small"}, code=400)

    if replace_dist:
        store.set_distribution(distribution)

    balances = spot.balances()
    usdt_avail = balances["USDT"]
    usdt_needed = sum(v * 0.01 * amount for v in distribution.values())
    if usdt_avail < usdt_needed:
        return jsonify({"msg": "Not enough USDT available"}, code=400)

    purchase = {}
    for asset, fraction in distribution.items():
        price = tickers[asset][0]
        funds = amount * fraction * 0.01
        qty = funds / price
        purchase[asset] = [qty, price]
        if is_mock:
            continue
        print(f"Buying {qty} {asset} @ ${price} for ${funds}")
        spot.place_buy_limit_order(asset, price, qty)
    store.add_purchase(purchase, mock=is_mock)
    return jsonify({})


# TODO: Rebalance and selling proportions/amounts

@app.route('/sell', methods=['POST'])
@needs_code
def sell():
    for sym, qty in spot.balances().items():
        if sym == "USDT":
            continue
        price = tickers[sym]
        if price * float(qty) < 2 or (sym == "BTC" and float(qty) < 0.0001):
            continue
        print(f"Selling {qty} of {sym} @ {price}")
        spot.place_sell_limit_order(sym, price, qty)
