"""Config schema and semantic validation (spec 6.1, R19): every error names its key path."""

from typing import Any

import pytest

from homematic_exporter.metrics import ConfigError, parse_config
from tests.metrics.conftest import metric


def errors(raw: dict[str, Any]) -> str:
    with pytest.raises(ConfigError) as info:
        parse_config(raw)
    return str(info.value)


def with_metrics(raw: dict[str, Any], *entries: dict[str, Any]) -> dict[str, Any]:
    raw["metrics"] = list(entries)
    return raw


def test_valid_config_parses(raw_config: dict[str, Any]) -> None:
    config = parse_config(
        with_metrics(raw_config, metric(scale=0.01, transform={"in": ["OPEN", "TILTED"]}))
    )
    assert config.metrics[0].scale == 0.01
    assert config.metrics[0].transform.kind == "in"
    assert config.extract.system_room == "system"


def test_spec_example_error_for_unknown_label(raw_config: dict[str, Any]) -> None:
    entries = [
        metric(name=f"homematic_room_thing{i}_celsius", labels=["room"]) for i in range(3)
    ] + [metric(labels=["room", "sgtin"])]
    assert "metrics[3].labels[1]: unknown label 'sgtin'" in errors(with_metrics(raw_config, *entries))


def test_label_must_be_available_for_the_scope(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(labels=["room", "device"])))
    assert "metrics[0].labels[1]: label 'device' is not available for scope 'rooms'" in msg


def test_duplicate_label_rejected(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(labels=["room", "room"])))
    assert "metrics[0].labels[1]: duplicate label 'room'" in msg


@pytest.mark.parametrize(
    "name",
    ["room_temperature_celsius", "homematic_Room_celsius", "homematic_", "homematic_a__b", "h"],
)
def test_bad_metric_names_rejected(raw_config: dict[str, Any], name: str) -> None:
    assert "metrics[0].name: invalid name" in errors(with_metrics(raw_config, metric(name=name)))


def test_gauge_must_not_end_in_total(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(name="homematic_room_events_total")))
    assert "metrics[0].name:" in msg
    assert "_total" in msg


def test_duplicate_name_names_both_entries(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(), metric()))
    assert "metrics[1].name: duplicate metric name" in msg
    assert "metrics[0]" in msg


def test_builtin_names_are_reserved(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(name="homematic_valves_open")))
    assert "metrics[0].name: " in msg
    assert "reserved" in msg


def test_unknown_scope_type_and_key(raw_config: dict[str, Any]) -> None:
    msg = errors(
        with_metrics(raw_config, metric(scope="houses"), metric(type="counter"), metric(colour=1))
    )
    assert "metrics[0].scope" in msg
    assert "metrics[1].type" in msg
    assert "metrics[2].colour: unknown key" in msg


def test_missing_required_key(raw_config: dict[str, Any]) -> None:
    entry = metric()
    del entry["help"]
    assert "metrics[0].help: missing required key" in errors(with_metrics(raw_config, entry))


def test_unknown_top_level_and_section_keys(raw_config: dict[str, Any]) -> None:
    raw_config["surprise"] = 1
    raw_config["tuning"]["nope"] = 2
    msg = errors(raw_config)
    assert "surprise: unknown key" in msg
    assert "tuning.nope: unknown key" in msg


def test_extract_errors_carry_their_path(raw_config: dict[str, Any]) -> None:
    raw_config["extract"]["rooms"]["bogus"] = "x"
    assert "extract.rooms" in errors(raw_config)


def test_value_must_exist_for_scope(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(value="rssi_dbm"), metric(value="name")))
    assert "metrics[0].value: unknown value 'rssi_dbm' for scope 'rooms'" in msg
    assert "metrics[1].value: unknown value 'name'" in msg


def test_extras_value_needs_a_matching_extract_entry(raw_config: dict[str, Any]) -> None:
    raw_config["extract"]["extras"] = [{"scope": "room", "key": "boost", "field": "boostDuration"}]
    ok = metric(name="homematic_room_boost_seconds", value="extras.boost")
    assert parse_config(with_metrics(raw_config, ok)).metrics[0].value == "extras.boost"
    wrong_scope = metric(name="homematic_device_boost_seconds", scope="devices", value="extras.boost")
    unknown = metric(name="homematic_room_other_seconds", value="extras.other")
    msg = errors(with_metrics(raw_config, wrong_scope, unknown))
    assert "metrics[0].value: no extract.extras entry with scope 'device' and key 'boost'" in msg
    assert "metrics[1].value: no extract.extras entry with scope 'room' and key 'other'" in msg


def test_batteries_scope_has_no_extras(raw_config: dict[str, Any]) -> None:
    raw_config["extract"]["extras"] = [{"scope": "device", "key": "x", "field": "f"}]
    entry = metric(
        name="homematic_battery_x_seconds", scope="batteries", value="extras.x", labels=["device"]
    )
    assert "metrics[0].value" in errors(with_metrics(raw_config, entry))


@pytest.mark.parametrize(
    "transform",
    ["sometimes", {"equals": []}, {"in": "OPEN"}, {"in": []}, {"equals": 1, "in": [1]}, {}, 3],
)
def test_bad_transforms_rejected(raw_config: dict[str, Any], transform: object) -> None:
    assert "metrics[0].transform" in errors(with_metrics(raw_config, metric(transform=transform)))


@pytest.mark.parametrize("transform", ["none", "bool", {"equals": "AUTOMATIC"}, {"in": ["A", 1]}])
def test_good_transforms_accepted(raw_config: dict[str, Any], transform: object) -> None:
    parse_config(with_metrics(raw_config, metric(transform=transform)))


def test_transform_in_is_bounded(raw_config: dict[str, Any]) -> None:
    big = {"in": [str(i) for i in range(1000)]}
    assert "metrics[0].transform" in errors(with_metrics(raw_config, metric(transform=big)))


@pytest.mark.parametrize("scale", ["2", True, None, float("nan"), float("inf"), [1], "0.01"])
def test_bad_scale_rejected(raw_config: dict[str, Any], scale: object) -> None:
    assert "metrics[0].scale" in errors(with_metrics(raw_config, metric(scale=scale)))


def test_integer_scale_is_accepted(raw_config: dict[str, Any]) -> None:
    assert parse_config(with_metrics(raw_config, metric(scale=2))).metrics[0].scale == 2.0


@pytest.mark.parametrize("field", ["name", "help", "value"])
def test_wrong_types_rejected(raw_config: dict[str, Any], field: str) -> None:
    assert f"metrics[0].{field}" in errors(with_metrics(raw_config, metric(**{field: 5})))


def test_oversized_text_rejected(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(help="x" * 10_000, name="homematic_" + "a" * 500)))
    assert "metrics[0].help" in msg
    assert "metrics[0].name" in msg


def test_too_many_metrics_rejected(raw_config: dict[str, Any]) -> None:
    entries = [metric(name=f"homematic_room_m{i}_celsius") for i in range(501)]
    assert "metrics:" in errors(with_metrics(raw_config, *entries))


def test_metrics_key_required_and_must_be_a_list(raw_config: dict[str, Any]) -> None:
    del raw_config["metrics"]
    assert "metrics: missing required key" in errors(raw_config)
    raw_config["metrics"] = {"a": 1}
    assert "metrics" in errors(raw_config)


def test_version_must_be_one(raw_config: dict[str, Any]) -> None:
    raw_config["version"] = 2
    assert "version" in errors(raw_config)


def test_top_level_must_be_a_mapping() -> None:
    with pytest.raises(ConfigError, match="mapping"):
        parse_config(["a"])


def test_retention_days_upper_bound(raw_config: dict[str, Any]) -> None:
    raw_config["tuning"]["state_retention_days"] = 10**30
    assert "tuning.state_retention_days" in errors(raw_config)


def test_non_finite_tuning_rejected(raw_config: dict[str, Any]) -> None:
    raw_config["tuning"]["heat_demand_min_position"] = float("nan")
    assert "tuning.heat_demand_min_position" in errors(raw_config)


def test_errors_are_collected_and_capped(raw_config: dict[str, Any]) -> None:
    entries = [metric(name=f"homematic_room_m{i}_celsius", labels=["bad"]) for i in range(100)]
    err = pytest.raises(ConfigError, parse_config, with_metrics(raw_config, *entries)).value
    assert len(err.issues) == 100
    assert len(str(err).splitlines()) < 40
    assert "more" in str(err)


def test_errors_never_echo_secret_looking_values(raw_config: dict[str, Any]) -> None:
    secret = "token=SUPERSECRET123"
    sgtin = "3014F711A000" + "0123456789AB"
    msg = errors(
        with_metrics(
            raw_config,
            metric(labels=[secret, sgtin]),
            metric(name=f"bad name {sgtin.lower()}"),
        )
    )
    assert "SUPERSECRET123" not in msg
    assert sgtin not in msg
    assert sgtin.lower() not in msg
    assert "metrics[0].labels[0]: unknown label" in msg
    assert "metrics[1].name: invalid name" in msg


def test_long_echoed_values_are_truncated(raw_config: dict[str, Any]) -> None:
    msg = errors(with_metrics(raw_config, metric(labels=["x" * 500])))
    assert "x" * 100 not in msg


def test_unknown_key_names_are_truncated_and_scrubbed(raw_config: dict[str, Any]) -> None:
    raw_config["authToken=SECRETVALUE" + "k" * 300] = 1
    msg = errors(raw_config)
    assert "SECRETVALUE" not in msg
    assert "k" * 100 not in msg
