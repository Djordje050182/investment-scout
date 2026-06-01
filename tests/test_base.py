# tests/test_base.py
import pandas as pd
from engine.adapters.base import MarketData


def test_marketdata_holds_fields():
    df = pd.DataFrame({"Close": [1.0, 2.0]})
    md = MarketData(symbol="AAPL", market="US", prices=df,
                    fundamentals={"roe": 0.2}, price=2.0)
    assert md.symbol == "AAPL"
    assert md.market == "US"
    assert md.price == 2.0
    assert md.fundamentals["roe"] == 0.2
    assert md.prices.iloc[-1]["Close"] == 2.0
