"""Battery history (spec 8): low-since / last-replaced per device name, persisted as `battery`."""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from homematic_exporter.config_models import Tuning
from homematic_exporter.contracts import BatteryRecord, Device, StateStore

logger = logging.getLogger(__name__)

KEY = "battery"
_VERSION = 1

# Internal record: BatteryRecord fields plus `last_seen_day` (ISO date, UTC).
_Stored = dict[str, object]


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class BatteryHistory:
    def __init__(self, store: StateStore, tuning: Tuning) -> None:
        self._store = store
        self._retention = timedelta(days=tuning.state_retention_days)
        self._records: dict[str, _Stored] = self._load()

    def _load(self) -> dict[str, _Stored]:
        data = self._store.load(KEY)
        records: dict[str, _Stored] = {}
        raw = data.get("records") if data else None
        if not isinstance(raw, dict):
            return records
        for name, rec in raw.items():
            seen = _day(rec.get("last_seen_day")) if isinstance(rec, dict) else None
            if not isinstance(name, str) or not isinstance(rec, dict) or seen is None:
                logger.warning("dropping malformed battery history record")
                continue
            records[name] = {
                "room": _text(rec.get("room")),
                "device_type": _text(rec.get("device_type")),
                "low_since": _num(rec.get("low_since")),
                "last_replaced": _num(rec.get("last_replaced")),
                "last_seen_day": seen.isoformat(),
            }
        return records

    def update(self, devices: Sequence[Device], now: float) -> list[BatteryRecord]:
        today = datetime.fromtimestamp(now, UTC).date()
        today_s = today.isoformat()
        dirty = False
        result: list[BatteryRecord] = []

        for dev in devices:
            rec = self._records.get(dev.name)
            if rec is None:
                low_since = now if dev.low_battery is True and dev.unreachable is not True else None
                rec = {
                    "room": dev.room,
                    "device_type": dev.device_type,
                    "low_since": low_since,
                    "last_replaced": None,
                    "last_seen_day": today_s,
                }
                self._records[dev.name] = rec
                dirty = True
            else:
                if rec["room"] != dev.room or rec["device_type"] != dev.device_type:
                    rec["room"], rec["device_type"] = dev.room, dev.device_type
                    dirty = True
                if dev.unreachable is not True and dev.low_battery is not None:
                    was_low = rec["low_since"] is not None
                    if dev.low_battery and not was_low:
                        rec["low_since"] = now
                        dirty = True
                    elif not dev.low_battery and was_low:
                        rec["last_replaced"] = now
                        rec["low_since"] = None
                        dirty = True
                if rec["last_seen_day"] != today_s:
                    rec["last_seen_day"] = today_s
                    dirty = True
            result.append(
                BatteryRecord(
                    device=dev.name,
                    room=dev.room,
                    device_type=dev.device_type,
                    low_since=_num(rec["low_since"]),
                    last_replaced=_num(rec["last_replaced"]),
                )
            )

        cutoff = today - self._retention
        for name in [n for n, r in self._records.items() if _is_older(r, cutoff)]:
            del self._records[name]
            dirty = True

        if dirty:
            self._store.save(KEY, {"version": _VERSION, "records": self._records})
        return result


def _is_older(rec: _Stored, cutoff: date) -> bool:
    seen = _day(rec["last_seen_day"])
    return seen is not None and seen < cutoff
