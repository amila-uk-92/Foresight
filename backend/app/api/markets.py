"""Registered markets: what can be imported and forecast, and on which rules."""

from fastapi import APIRouter, HTTPException
from backend.app.markets import get_market, markets, source_for
from backend.app.forecasting.contracts import SPECIALIST_MARKETS

router = APIRouter(prefix="/api/markets", tags=["markets"])


def describe(market):
    return {
        **market.summary(),
        "source_label": source_for(market).label,
        "forecasting_enabled": market.symbol
        in SPECIALIST_MARKETS.get(market.specialist, ()),
    }


@router.get("")
def list_markets():
    return {"markets": [describe(m) for m in markets()]}


@router.get("/{symbol}")
def market_detail(symbol: str):
    market = get_market(symbol, None)
    if market is None:
        raise HTTPException(404, f"Unsupported symbol '{symbol}'")
    return describe(market)
