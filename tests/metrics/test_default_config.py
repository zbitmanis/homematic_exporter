"""The bundled default `metrics:` list against a hand-built snapshot (golden exposition).

The fixture-through-parser golden test is task 4; here the snapshot is built by hand so the
metrics module is tested alone. To regenerate the golden file after a deliberate change, run
`python -m tests.metrics.test_default_config` from the repo root and review the diff.
"""

from pathlib import Path

from homematic_exporter.contracts import BatteryRecord, Snapshot
from homematic_exporter.metrics import Registry, load_config, parse_config, render
from tests.conftest import DEFAULT_CONFIG
from tests.metrics.helpers import contact, device, parse, room, snapshot, valve

GOLDEN = Path(__file__).parent / "golden" / "default_config.prom"
EXPECTED_NAMES = {
    "homematic_room_temperature_celsius",
    "homematic_room_setpoint_celsius",
    "homematic_room_humidity_ratio",
    "homematic_room_automatic_mode",
    "homematic_room_window_open",
    "homematic_valve_position_ratio",
    "homematic_valve_actual_temperature_celsius",
    "homematic_contact_open",
    "homematic_device_low_battery",
    "homematic_device_unreachable",
    "homematic_device_undervoltage",
    "homematic_device_rssi_dbm",
    "homematic_device_battery_low_since_timestamp_seconds",
    "homematic_device_battery_last_replaced_timestamp_seconds",
}


def golden_input() -> tuple[Snapshot, tuple[BatteryRecord, ...]]:
    """Three rooms (one with a dead sensor), four devices, three valves, one contact."""
    snap = snapshot(
        rooms=(
            room("kitchen"),
            room(
                "living",
                temperature_celsius=20.0,
                humidity=48.5,
                control_mode="MANUAL",
                window_state="TILTED",
            ),
            room("girts", temperature_celsius=None, humidity=None, window_state=None),
        ),
        devices=(
            device("kitchen wall-thermostat", "kitchen"),
            device(
                "living radiator-thermostat",
                "living",
                device_type="radiator-thermostat",
                low_battery=True,
                rssi_dbm=-81,
            ),
            device(
                "girts temp-humidity-display",
                "girts",
                device_type="temp-humidity-display",
                unreachable=True,
                rssi_dbm=None,
            ),
            device(
                "system access-point",
                "system",
                device_type="access-point",
                low_battery=None,
                undervoltage=True,
            ),
        ),
        valves=(
            valve("kitchen floor-valve", 0.35),
            valve(
                "living radiator-thermostat",
                0.0,
                room="living",
                device_type="radiator-thermostat",
                actual_temperature_celsius=19.5,
            ),
            valve(
                "girts radiator-thermostat", None, room="girts", device_type="radiator-thermostat"
            ),
        ),
        contacts=(contact(window_state="OPEN"),),
    )
    batteries = (
        BatteryRecord(
            "living radiator-thermostat",
            "living",
            "radiator-thermostat",
            1_760_000_000.0,
            1_750_000_000.0,
        ),
        BatteryRecord("kitchen wall-thermostat", "kitchen", "wall-thermostat", None, None),
    )
    return snap, batteries


def render_golden() -> bytes:
    snap, batteries = golden_input()
    return render(load_config(DEFAULT_CONFIG), snap, batteries, version="1.2.3")


def test_default_config_defines_the_catalogue() -> None:
    names = [m.name for m in load_config(DEFAULT_CONFIG).metrics]
    assert set(names) == EXPECTED_NAMES
    assert len(names) == len(EXPECTED_NAMES)


def test_golden_exposition() -> None:
    assert render_golden() == GOLDEN.read_bytes()


def test_golden_series_follow_the_spec_rules() -> None:
    s = parse(render_golden())
    assert len(s["homematic_room_temperature_celsius"]) == 2  # girts has no temperature (R8)
    assert sorted(s["homematic_room_humidity_ratio"].values()) == [0.485, 0.55]  # R10
    assert s["homematic_valves_open"] == {(): 1.0}
    assert s["homematic_heat_demand"] == {(): 1.0}
    assert len(s["homematic_device_low_battery"]) == 3  # one device has no value
    assert len(s["homematic_device_rssi_dbm"]) == 3
    assert list(s["homematic_device_battery_low_since_timestamp_seconds"].values()) == [1.76e9]


def test_series_count_stays_near_the_captured_installation() -> None:
    """12 rooms, 20 devices, 15 valves, 1 contact: about 230 series (spec 6.7, R9)."""
    config = load_config(DEFAULT_CONFIG)
    registry = Registry.build(config.metrics, config.tuning)
    snap = snapshot(
        rooms=tuple(room(f"r{i}") for i in range(12)),
        devices=tuple(device(f"r{i} d{j}", f"r{i}") for i in range(10) for j in range(2)),
        valves=tuple(valve(f"r{i} v") for i in range(15)),
        contacts=(contact(),),
    )
    registry.update(snap)
    count = sum(
        len(v) for name, v in parse(registry.exposition()).items() if name in EXPECTED_NAMES
    )
    assert 150 <= count <= 260


def test_default_config_text_is_valid_for_parse_config() -> None:
    import yaml

    assert parse_config(yaml.safe_load(DEFAULT_CONFIG.read_text())).metrics


if __name__ == "__main__":  # pragma: no cover
    GOLDEN.write_bytes(render_golden())
