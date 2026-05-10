def calculate_position_size(balance, risk_percent, entry_price, stop_loss):
    """
    Математический расчет объема позиции для контроля убытков.
    """
    try:
        balance = float(balance)
        risk_percent = float(risk_percent)
        entry_price = float(entry_price)
        stop_loss = float(stop_loss)

        if entry_price == stop_loss or entry_price <= 0:
            return 0.0

        # Сколько денег мы готовы потерять в этой сделке
        risk_amount = balance * (risk_percent / 100)

        # Разница в цене до стоп-лосса
        price_risk = abs(entry_price - stop_loss)

        if price_risk == 0:
            return 0.0

        # Объем позиции (лоты/монеты)
        size = risk_amount / price_risk
        return round(size, 4)
    except Exception:
        return 0.0