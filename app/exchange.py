from typing import Dict, List

import gate_api


class Client:
    def balances(self) -> Dict[str, float]:
        raise NotImplementedError

    def tickers(self) -> Dict[str, List[float]]:
        raise NotImplementedError

    def place_buy_limit_order(self, asset: str, price: float, qty: float):
        raise NotImplementedError

    def place_sell_limit_order(self, asset: str, price: float, qty: float):
        raise NotImplementedError


class GateioSpot(Client):
    def __init__(self, key, secret):
        config = gate_api.Configuration(
            host="https://api.gateio.ws/api/v4",
            key=key,
            secret=secret
        )
        self._api = gate_api.ApiClient(config)
        self._spot = gate_api.SpotApi(self._api)

    def balances(self):
        balances = {}
        resp = self._spot.list_spot_accounts()
        for item in resp:
            sym, qty = item.currency, float(item.available)
            balances[sym] = qty
        return balances

    def tickers(self):
        tickers = {}
        for info in self._spot.list_tickers():
            if not info.currency_pair.endswith("_USDT"):
                continue
            if info.etf_leverage is not None:
                continue
            asset = info.currency_pair.replace("_USDT", "")
            tickers[asset] = [float(info.last), float(info.change_percentage)]
        return tickers

    def place_buy_limit_order(self, asset, price, qty):
        self._spot.create_order(gate_api.Order(
            account="spot",
            amount=str(qty),
            price=price,
            currency_pair=f"{asset}_USDT",
            side="buy",
            time_in_force="gtc",
        ))

    def place_sell_limit_order(self, asset, price, qty):
        self._spot.create_order(gate_api.Order(
            account="spot",
            amount=str(qty),
            price=price,
            currency_pair=f"{asset}_USDT",
            side="sell",
            time_in_force="gtc",
        ))
