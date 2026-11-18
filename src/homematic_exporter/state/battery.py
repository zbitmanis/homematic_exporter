"""Battery history (spec 8): low-since / last-replaced per device name, persisted as `battery`."""

import logging
import math
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from homematic_exporter.config_models import Tuning
from homematic_exporter.contracts import BatteryRecord, Device, StateStore

logger = logging.getLogger(__name__)

KEY = "battery"
_VERSION = 1

# Internal record: BatteryRecord fields plus `last_seen_day` (ISO date, UTC).
_Stored = dict[str, object]


def _opt_num(value: object) -> float | None:
    """None stays None; a finite non-bool number becomes float; anything else is malformed."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("not a number")
    number = float(value)  # OverflowError (huge int) is handled by the caller
    if not math.isfinite(number):
        raise ValueError("not finite")
    return number


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


class BatteryHistory:
    def __init__(self, store: StateStore, tuning: Tuning) -> None:
        self._store = store
        self._retention = timedelta(days=tuning.state_retention_days)
        self._unsaved = False  # a change that has not reached the store yet
        self._records: dict[str, _Stored] = self._load()

    def _load(self) -> dict[str, _Stored]:
        data = self._store.load(KEY)
        records: dict[str, _Stored] = {}
        if not data:
            return records
        raw = data.get("records")
        if data.get("version") != _VERSION or not isinstance(raw, dict):
            logger.warning("battery history has an unknown format; starting empty")
            self._unsaved = True
            return records
        for name, rec in raw.items():
            try:
                if not isinstance(rec, dict):
                    raise ValueError("record is not an object")
                records[name] = {
                    "room": _text(rec.get("room")),
                    "device_type": _text(rec.get("device_type")),
                    "low_since": _opt_num(rec.get("low_since")),
                    "last_replaced": _opt_num(rec.get("last_replaced")),
                    "last_seen_day": date.fromisoformat(str(rec.get("last_seen_day"))).isoformat(),
                }
            except (ValueError, TypeError, OverflowError):
                logger.warning("dropping malformed battery history record")
                self._unsaved = True  # rewrite the store without it
        return records

    def update(self, devices: Sequence[Device], now: float) -> list[BatteryRecord]:
        try:
            if not math.isfinite(now):
                raise ValueError
            today = datetime.fromtimestamp(now, UTC).date()
        except (ValueError, OverflowError, OSError):
            raise ValueError("invalid timestamp") from None
        today_s = today.isoformat()
        dirty = self._unsaved
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
                    low_since=_float(rec["low_since"]),
                    last_replaced=_float(rec["last_replaced"]),
                )
            )

        cutoff = today - self._retention
        for name in [n for n, r in self._records.items() if _is_older(r, cutoff)]:
            del self._records[name]
            dirty = True

        self._unsaved = dirty
        if dirty:
            try:
                self._store.save(KEY, {"version": _VERSION, "records": self._records})
            except OSError as exc:
                # Keep serving; the next update retries because `_unsaved` stays set.
                logger.warning("battery history save failed (%s); will retry", type(exc).__name__)
            else:
                self._unsaved = False
        return result


def _float(value: object) -> float | None:
    return value if isinstance(value, float) else None


def _is_older(rec: _Stored, cutoff: date) -> bool:
    # `_load` and `update` guarantee a valid ISO date. A future date is simply not pruned
    # until time catches up.
    return date.fromisoformat(str(rec["last_seen_day"])) < cutoff
