import requests
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class TInvestClient:
    def __init__(self):
        self.token = config.T_INVEST_TOKEN
        self.base_url = "https://invest-public-api.tinkoff.ru/rest"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_market_price(self, figi):
        """
        Получает последнюю цену по FIGI инструмента (идентификатор Тинькофф).
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.itf.v1.MarketDataService/GetLastPrices"
        payload = {"figi": [figi]}

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            data = response.json()
            # Цена в Тинькофф API приходит в виде 'units' и 'nano'
            price_data = data['lastPrices'][0]['price']
            price = price_data['units'] + price_data['nano'] / 1e9
            return price
        except Exception as e:
            return f"Error: {e}"

# Примеры FIGI: BBG004730N88 (SBER), BBG004731354 (GAZP)