"""The bundled default config must load into the shared models and cover the mini fixture."""

from typing import Any

from homematic_exporter.config_models import ExtractConfig, Tuning


def test_default_extract_and_tuning_load(
    default_extract: ExtractConfig, default_tuning: Tuning
) -> None:
    assert default_extract.system_room == "system"
    assert default_extract.room_group_type == "HEATING"
    assert default_tuning.heat_demand_min_position == 0.0
    assert default_tuning.state_retention_days == 90


def test_default_maps_every_model_in_the_fixture_except_the_unmapped_one(
    default_extract: ExtractConfig, mini_state: dict[str, Any]
) -> None:
    models = {d["modelType"] for d in mini_state["devices"].values()}
    assert models - set(default_extract.device_models) == {"HmIP-NEW-1"}


def test_default_rules_match_channel_types_in_the_fixture(
    default_extract: ExtractConfig, mini_state: dict[str, Any]
) -> None:
    channel_types = {
        c["functionalChannelType"]
        for d in mini_state["devices"].values()
        for c in d["functionalChannels"].values()
    }
    rule_types = [r.channel_type for r in default_extract.valves]
    rule_types += [r.channel_type for r in default_extract.contacts]
    assert set(rule_types) <= channel_types
