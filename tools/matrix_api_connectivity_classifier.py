"""MATRIX API connectivity evidence classifier. Offline: no secrets or network calls."""
import json
import os
from datetime import datetime, timezone

def classify(provider, *, http_status=None, authenticated=False, payload_valid=False):
    if http_status is None:
        status = "NOT_TESTED"
    elif http_status in (401, 403):
        status = "AUTHENTICATION_OR_ENTITLEMENT_FAILED"
    elif http_status == 429:
        status = "QUOTA_OR_RATE_LIMIT"
    elif http_status == 200 and authenticated and payload_valid:
        status = "VERIFIED_RESPONSE"
    else:
        status = "UNVERIFIED_RESPONSE"
    return {"provider": provider, "status": status, "http_status": http_status,
            "authenticated": authenticated, "payload_valid": payload_valid,
            "real_money": "BLOCKED", "automatic_wagering": False}

def secret_presence(env=None):
    """Report names and presence only; never disclose secret contents."""
    values = os.environ if env is None else env
    mapping = {"api_football": "API_FOOTBALL_KEY", "rapidapi_tennis": "RAPIDAPI_TENNIS_KEY",
               "api_tennis": "API_TENNIS_KEY", "odds_api_net": "ODDS_API_NET_KEY"}
    return {provider: {"secret_name": key, "configured": bool(values.get(key, "").strip()),
                       "live_connectivity_verified": False} for provider, key in mapping.items()}


if __name__ == "__main__":
    print(json.dumps({"schema":"MATRIX_API_CONNECTIVITY_CLASSIFIER_V1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "providers":[classify(x) for x in ("api_football","api_tennis","rapidapi_tennis")],
        "credential_presence": secret_presence(),
        "note":"No live credential test was performed"}, indent=2))
