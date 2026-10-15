from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
ROLLOVER_HOUR_BOGOTA = 15


def resolve_world_date(now: datetime, rollover_hour: int = ROLLOVER_HOUR_BOGOTA) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
    if not 0 <= int(rollover_hour) <= 23:
        raise ValueError("ROLLOVER_HOUR_OUT_OF_RANGE")
    local = now.astimezone(BOGOTA)
    target = local.date() + (timedelta(days=1) if local.hour >= int(rollover_hour) else timedelta())
    return target.isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now-utc")
    parser.add_argument("--rollover-hour", type=int, default=ROLLOVER_HOUR_BOGOTA)
    args = parser.parse_args()

    if args.now_utc:
        now = datetime.fromisoformat(args.now_utc.replace("Z", "+00:00"))
    else:
        now = datetime.now(timezone.utc)
    print(resolve_world_date(now, args.rollover_hour))


if __name__ == "__main__":
    main()
