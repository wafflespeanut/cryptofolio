import dbm
import functools
import json
import os
import gate_api
from datetime import datetime
from flask import Flask, request


# (.*)\t(.*)%$
# "$1": $2,

class Storage:
    KEY_DISTRIBUTION = b"dist"
    TIME_FORMAT = "%Y%m%d"

    def __init__(self, path):
        self.path = path

    def load_distribution(self):
        with dbm.open(self.path, "c") as db:
            if db.get(self.KEY_DISTRIBUTION) is None:
                db[self.KEY_DISTRIBUTION] = json.dumps({})
            return json.loads(db[self.KEY_DISTRIBUTION])

    def set_distribution(self, dist):
        with dbm.open(self.path, "c") as db:
            db[self.KEY_DISTRIBUTION] = json.dumps(dist)

    def add_purchase(self, data):
        with dbm.open(self.path, "c") as db:
            key = str(int(datetime.strptime(datetime.now().strftime(self.TIME_FORMAT), self.TIME_FORMAT).timestamp()))
            prev = db.get(key)
            if prev is not None:
                for k, v in json.loads(prev).items():
                    if data.get(k) is None:
                        data[k] = [0, 0]
                    data[k][1] = round((data[k][0] * data[k][1] + v[0] * v[1]) / (data[k][0] + v[0]), 4)
                    data[k][0] += v[0]
            db[key] = json.dumps(data)

    def list_purchases(self):
        data = []
        with dbm.open(self.path, "c") as db:
            for k in db.keys():
                if k == self.KEY_DISTRIBUTION:
                    continue
                data.append([int(k), json.loads(db[k])])
        data.sort(key=lambda i: i[0])
        return data


secret_code = os.environ["ACCESS_CODE"]
app = Flask("Cryptofolio")
store = Storage(os.environ["DATA"])
api_key, api_secret = os.environ["GATE_IO_KEY"], os.environ["GATE_IO_SECRET"]
configuration = gate_api.Configuration(
    host="https://api.gateio.ws/api/v4",
    key=api_key,
    secret=api_secret
)
api_client = gate_api.ApiClient(configuration)
spot = gate_api.SpotApi(api_client)


def needs_code(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if request.args.get("code") != secret_code:
            return jsonify({}, code=401)
        return f(*args, **kwargs)
    return wrapped


def get_tickers():
    tickers = {}
    for info in spot.list_tickers():
        if not info.currency_pair.endswith("_USDT"):
            continue
        if info.etf_leverage is not None:
            continue
        asset = info.currency_pair.replace("_USDT", "")
        tickers[asset] = [float(info.last), float(info.change_percentage)]
    return tickers


def jsonify(data, code=200):
    return app.response_class(
        response=json.dumps(data),
        status=code,
        mimetype="application/json",
    )


@app.route('/tickers', methods=['GET'])
@needs_code
def tickers():
    return jsonify({
        "tickers": get_tickers(),
        "distribution": store.load_distribution(),
    })


@app.route('/purchases', methods=['GET'])
@needs_code
def purchases():
    purchases = store.list_purchases()
    return jsonify(purchases)


@app.route('/balances', methods=['GET'])
@needs_code
def balances():
    tickers = get_tickers()
    balances = {}
    resp = spot.list_spot_accounts()
    total = 0
    for item in resp:
        sym, qty = item.currency, float(item.available)
        price = 1 if sym == "USDT" else tickers[sym][0]
        if price * float(qty) < 2:
            sym = "Others"
        balances.setdefault(sym, [0, 0])
        total += price * float(qty)
        balances[sym][0] += price * float(qty)
    for sym in balances:
        balances[sym][1] = balances[sym][0] / total
    return jsonify(balances)


@app.route('/buy', methods=['POST'])
@needs_code
def buy():
    distribution = request.json
    if sum(v for v in distribution.values()) != 100:
        return jsonify({"msg": "Sum is not 100%"}, code=400)
    tickers = get_tickers()
    for k in distribution:
        if tickers.get(k) is None:
            return jsonify({"msg": f"{k} missing in exchange"}, code=400)
    store.set_distribution(distribution)
    resp = spot.list_spot_accounts(currency="USDT")
    usdt_avail = float(resp[0].available)
    amount = float(request.args["amount"])
    usdt_needed = sum(v * 0.01 * amount for v in distribution.values())
    if usdt_avail < usdt_needed:
        return jsonify({"msg": "Not enough USDT available"}, code=400)

    purchase = {}
    for asset, fraction in distribution.items():
        price = tickers[asset][0]
        funds = amount * fraction * 0.01
        qty = funds / price
        print(f"Buying {qty} {asset} @ ${price} for ${funds}")
        if request.args.get("mock") is not None:
            continue
        purchase[asset] = [qty, price]
        spot.create_order(gate_api.Order(
            account="spot",
            amount=str(qty),
            price=price,
            currency_pair=f"{asset}_USDT",
            side="buy",
            time_in_force="gtc",
        ))
    store.add_purchase(purchase)
    return jsonify(store.list_purchases())


# TODO: Rebalance and selling proportions/amounts

@app.route('/sell', methods=['POST'])
@needs_code
def sell():
    resp = spot.list_spot_accounts()
    for item in resp:
        sym, qty = item.currency, item.available
        if sym == "USDT":
            continue
        price = tickers[sym]
        if price * float(qty) < 2 or (sym == "BTC" and float(qty) < 0.0001):
            continue
        print(f"Selling {qty} of {sym} @ {price}")
        spot.create_order(gate_api.Order(
            account="spot",
            amount=str(qty),
            price=price,
            currency_pair=f"{sym}_USDT",
            side="sell",
            time_in_force="gtc",
        ))


app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
