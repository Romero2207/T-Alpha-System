import pandas as pd
from pybit.unified_trading import HTTP
import requests
import config

class MarketGateway:
    def __init__(self):
        self.session_bybit = HTTP(testnet=False)
        self.t_token = str(config.T_INVEST_TOKEN).strip()

    def get_crypto_symbols(self):
        """Динамический список всех USDT пар с Bybit"""
        try:
            res = self.session_bybit.get_instruments_info(category="linear")
            return sorted([item['symbol'] for item in res['result']['list'] if item['quoteCoin'] == 'USDT'])
        except:
            return ["BTCUSDT", "ETHUSDT"]

    def get_stock_assets(self):
        """Динамический список акций из Тинькофф"""
        url = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.itf.v1.InstrumentsService/Shares"
        headers = {"Authorization": f"Bearer {self.t_token}", "Content-Type": "application/json"}
        try:
            r = requests.post(url, json={"instrumentStatus": "INSTRUMENT_STATUS_BASE"}, headers=headers)
            shares = r.json().get('instruments', [])
            return {s['ticker']: s['figi'] for s in shares}
        except:
            return {"SBER": "BBG004730N88"}

    def get_price(self, symbol, market_type, figi=None):
        if market_type == "Крипто":
            try:
                res = self.session_bybit.get_tickers(category="linear", symbol=symbol)
                return float(res['result']['list'][0]['lastPrice'])
            except: return 0.0
        else:
            url = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.itf.v1.MarketDataService/GetLastPrices"
            headers = {"Authorization": f"Bearer {self.t_token}", "Content-Type": "application/json"}
            try:
                r = requests.post(url, json={"figi": [figi]}, headers=headers)
                p = r.json()['lastPrices'][0]['price']
                return float(p['units']) + p['nano'] / 1e9
            except: return 0.0

    def get_ohlc(self, symbol, market_type):
        """Метод получения свечей для графиков"""
        if market_type == "Крипто":
            try:
                res = self.session_bybit.get_kline(category="linear", symbol=symbol, interval="60", limit=100)
                raw = res['result']['list'][::-1]
                df = pd.DataFrame(raw, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'Turnover'])
                df['Time'] = pd.to_datetime(df['Time'].astype(float), unit='ms')
                for col in ['Open', 'High', 'Low', 'Close']: df[col] = pd.to_numeric(df[col])
                return df
            except: return pd.DataFrame()
        return pd.DataFrame()