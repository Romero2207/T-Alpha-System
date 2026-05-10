from pybit.unified_trading import HTTP
def check_price(symbol="BTCUSDT"):
    try:
        session = HTTP(testnet=False)
        res = session.get_tickers(category="linear", symbol=symbol)
        return res['result']['list'][0]['lastPrice']
    except:
        return "0.0"