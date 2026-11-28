"""Read-only, fail-closed validation of already structured football market evidence.

Not a Luckia adapter: global page text or accessibility titles are insufficient.
"""
import math


def validate_full_match_over_25(event, market):
    """Return an exact quote only if event/market/selection identity is explicit."""
    if not isinstance(event, dict) or not isinstance(market, dict):
        return None
    event_id = event.get("event_id")
    market_id = market.get("market_id")
    if not event_id or not market_id or str(market.get("event_id")) != str(event_id):
        return None
    if market.get("period") != "FULL_MATCH" or market.get("market_type") != "TOTAL_GOALS":
        return None
    try:
        line = float(market.get("line"))
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(line) or line != 2.5:
        return None
    selections = market.get("selections")
    if not isinstance(selections, list):
        return None
    matching = [s for s in selections if isinstance(s, dict) and s.get("side") == "OVER"]
    if len(matching) != 1:
        return None
    selection = matching[0]
    selection_id = selection.get("selection_id")
    if not selection_id:
        return None
    try:
        price = float(selection.get("price"))
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(price) or price <= 1:
        return None
    return {"event_id": str(event_id), "market_id": str(market_id),
            "selection_id": str(selection_id), "market": "OVER_2_5", "price": price}
