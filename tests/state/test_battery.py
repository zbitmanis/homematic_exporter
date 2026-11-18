from datetime import UTC, datetime
from pathlib import Path

import pytest

from homematic_exporter.config_models import Tuning
from homematic_exporter.contracts import BatteryRecord, Device
from homematic_exporter.state import BatteryHistory, FileStateStore

DAY = 86400.0
T0 = datetime(2026, 3, 10, 12, 0, tzinfo=UTC).timestamp()


class MemStore:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, object]] = {}
        self.saves = 0

    def load(self, key: str) -> dict[str, object] | None:
        return self.data.get(key)

    def save(self, key: str, value: dict[str, object]) -> None:
        self.saves += 1
        self.data[key] = value


def dev(
    name: str = "kitchen thermostat",
    low: bool | None = False,
    unreachable: bool | None = False,
    room: str = "kitchen",
) -> Device:
    return Device(
        name=name,
        room=room,
        device_type="thermostat",
        low_battery=low,
        unreachable=unreachable,
        undervoltage=None,
        rssi_dbm=None,
        extras={},
    )


@pytest.fixture
def store() -> MemStore:
    return MemStore()


@pytest.fixture
def hist(store: MemStore) -> BatteryHistory:
    return BatteryHistory(store, Tuning())


def names(store: MemStore) -> list[str]:
    records = store.data["battery"]["records"]
    assert isinstance(records, dict)
    return list(records)


def one(records: list[BatteryRecord]) -> BatteryRecord:
    assert len(records) == 1
    return records[0]


def test_first_sight_ok_creates_empty_record(hist: BatteryHistory, store: MemStore) -> None:
    rec = one(hist.update([dev()], T0))
    assert rec == BatteryRecord("kitchen thermostat", "kitchen", "thermostat", None, None)
    assert store.saves == 1


def test_first_sight_low_reachable_sets_low_since(hist: BatteryHistory) -> None:
    assert one(hist.update([dev(low=True)], T0)).low_since == T0


def test_first_sight_low_unreachable_no_low_since(hist: BatteryHistory, store: MemStore) -> None:
    assert one(hist.update([dev(low=True, unreachable=True)], T0)).low_since is None
    assert store.saves == 1  # record still created


def test_first_sight_low_unknown_reachability_counts_as_reachable(hist: BatteryHistory) -> None:
    assert one(hist.update([dev(low=True, unreachable=None)], T0)).low_since == T0


def test_first_sight_unknown_flag_creates_record(hist: BatteryHistory) -> None:
    rec = one(hist.update([dev(low=None)], T0))
    assert rec.low_since is None and rec.last_replaced is None


def test_false_to_true_sets_low_since(hist: BatteryHistory) -> None:
    hist.update([dev(low=False)], T0)
    assert one(hist.update([dev(low=True)], T0 + 100)).low_since == T0 + 100


def test_true_to_false_sets_last_replaced_clears_low_since(hist: BatteryHistory) -> None:
    hist.update([dev(low=True)], T0)
    rec = one(hist.update([dev(low=False)], T0 + 100))
    assert rec.low_since is None and rec.last_replaced == T0 + 100


def test_stays_low_keeps_original_low_since(hist: BatteryHistory) -> None:
    hist.update([dev(low=True)], T0)
    assert one(hist.update([dev(low=True)], T0 + 100)).low_since == T0


def test_stays_ok_unchanged(hist: BatteryHistory) -> None:
    hist.update([dev(low=True)], T0)
    hist.update([dev(low=False)], T0 + 100)
    rec = one(hist.update([dev(low=False)], T0 + 200))
    assert rec.low_since is None and rec.last_replaced == T0 + 100


def test_unreachable_freezes_record(hist: BatteryHistory) -> None:
    hist.update([dev(low=True)], T0)
    rec = one(hist.update([dev(low=False, unreachable=True)], T0 + 100))
    assert rec.low_since == T0 and rec.last_replaced is None
    rec = one(hist.update([dev(low=False, unreachable=False)], T0 + 200))
    assert rec.low_since is None and rec.last_replaced == T0 + 200


def test_unreachable_no_false_to_true(hist: BatteryHistory) -> None:
    hist.update([dev(low=False)], T0)
    assert one(hist.update([dev(low=True, unreachable=True)], T0 + 100)).low_since is None


def test_unknown_flag_unchanged(hist: BatteryHistory) -> None:
    hist.update([dev(low=True)], T0)
    rec = one(hist.update([dev(low=None)], T0 + 100))
    assert rec.low_since == T0 and rec.last_replaced is None


def test_unreachable_device_counts_as_seen_and_is_not_pruned(store: MemStore) -> None:
    h = BatteryHistory(store, Tuning(state_retention_days=10))
    h.update([dev(low=True)], T0)
    for i in range(1, 30):
        h.update([dev(low=True, unreachable=True)], T0 + i * DAY)
    assert one(h.update([dev(low=True, unreachable=True)], T0 + 30 * DAY)).low_since == T0


def test_no_write_when_nothing_changed_same_day(hist: BatteryHistory, store: MemStore) -> None:
    hist.update([dev()], T0)
    hist.update([dev()], T0 + 60)
    hist.update([dev()], T0 + 3600)
    assert store.saves == 1


def test_one_extra_write_per_day(hist: BatteryHistory, store: MemStore) -> None:
    hist.update([dev()], T0)
    hist.update([dev()], T0 + DAY)
    hist.update([dev()], T0 + DAY + 60)
    assert store.saves == 2


def test_day_granularity_is_utc_midnight(hist: BatteryHistory, store: MemStore) -> None:
    late = datetime(2026, 3, 10, 23, 59, tzinfo=UTC).timestamp()
    hist.update([dev()], late)
    hist.update([dev()], late + 60)  # 00:00 next day
    assert store.saves == 2


def test_transition_writes(hist: BatteryHistory, store: MemStore) -> None:
    hist.update([dev(low=False)], T0)
    hist.update([dev(low=True)], T0 + 10)
    hist.update([dev(low=False)], T0 + 20)
    assert store.saves == 3


def test_persisted_shape_is_json_compatible(hist: BatteryHistory, store: MemStore) -> None:
    import json

    hist.update([dev(low=True)], T0)
    stored = json.loads(json.dumps(store.data["battery"]))
    rec = stored["records"]["kitchen thermostat"]
    assert rec["low_since"] == T0 and rec["last_seen_day"] == "2026-03-10"
    assert rec["last_replaced"] is None


def test_returns_only_passed_devices_in_order(hist: BatteryHistory) -> None:
    a, b = dev("a"), dev("b")
    hist.update([a, b], T0)
    assert [r.device for r in hist.update([b], T0 + 10)] == ["b"]
    assert [r.device for r in hist.update([b, a], T0 + 20)] == ["b", "a"]
    assert hist.update([], T0 + 30) == []


def test_records_are_per_device(hist: BatteryHistory) -> None:
    recs = hist.update([dev("a", low=True), dev("b", low=False)], T0)
    assert [r.low_since for r in recs] == [T0, None]


def test_renamed_device_is_new_record(hist: BatteryHistory) -> None:
    hist.update([dev("old", low=True)], T0)
    rec = one(hist.update([dev("new", low=True)], T0 + 100))
    assert rec.low_since == T0 + 100


def test_prune_after_retention(store: MemStore) -> None:
    h = BatteryHistory(store, Tuning(state_retention_days=5))
    h.update([dev("gone", low=True), dev("kept")], T0)
    h.update([dev("kept")], T0 + 5 * DAY)  # 5 days old: not older than 5
    assert "gone" in names(store)
    h.update([dev("kept")], T0 + 6 * DAY)
    assert names(store) == ["kept"]
    # a device that returns after pruning starts fresh
    assert one(h.update([dev("gone", low=False)], T0 + 7 * DAY)).low_since is None


def test_prune_triggers_save(store: MemStore) -> None:
    h = BatteryHistory(store, Tuning(state_retention_days=1))
    h.update([dev("gone")], T0)
    saves = store.saves
    h.update([], T0 + 2 * DAY)
    assert store.saves == saves + 1


def test_restart_reload_keeps_history(tmp_path: Path) -> None:
    fs = FileStateStore(tmp_path / "s")
    BatteryHistory(fs, Tuning()).update([dev(low=True)], T0)
    h2 = BatteryHistory(FileStateStore(tmp_path / "s"), Tuning())
    assert one(h2.update([dev(low=True)], T0 + 100)).low_since == T0
    rec = one(h2.update([dev(low=False)], T0 + 200))
    assert rec.last_replaced == T0 + 200


def test_restart_does_not_rewrite_same_day(tmp_path: Path, store: MemStore) -> None:
    BatteryHistory(store, Tuning()).update([dev()], T0)
    store.saves = 0
    BatteryHistory(store, Tuning()).update([dev()], T0 + 60)
    assert store.saves == 0


def test_corrupt_store_starts_empty(tmp_path: Path) -> None:
    fs = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "battery.json").write_text("{broken")
    assert one(BatteryHistory(fs, Tuning()).update([dev(low=True)], T0)).low_since == T0


@pytest.mark.parametrize(
    "data",
    [
        {"records": "x"},
        {"records": {"a": "x"}},
        {"records": {"a": {"last_seen_day": "bogus"}}},
        {"records": {"a": {"low_since": True}}},
        {},
    ],
)
def test_malformed_content_is_dropped_not_fatal(store: MemStore, data: dict[str, object]) -> None:
    store.data["battery"] = data
    h = BatteryHistory(store, Tuning())
    assert one(h.update([dev("a", low=False)], T0)).low_since is None


def test_time_is_injected_not_read(hist: BatteryHistory) -> None:
    assert one(hist.update([dev(low=True)], 12345.0)).low_since == 12345.0
