"""Pure parser from the raw Homematic IP configuration JSON to a `Snapshot` (spec 3, 4).

Every raw name, channel type and label comes from `ExtractConfig`; the structure (room joins,
naming, collision handling) is code. The raw input is untrusted: wrong types, missing keys and
non-finite numbers map to `None` and never raise. Only a payload that is not a configuration at
all (no `devices` or no `groups` object) raises `UpstreamError`. The parser logs nothing and
never mutates its input: collisions and unmapped models are returned in a `ParseReport` for the
sources to log once.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import (
    CollisionPolicy,
    Contact,
    Device,
    Extras,
    NameCollisionError,
    Room,
    Snapshot,
    UpstreamError,
    Valve,
)

# Channel types that carry the battery and radio fields of a device (spec 4).
_BASE_PREFIX = "DEVICE_BASE"
_BASE_TYPES = frozenset({"DEVICE_OPERATIONLOCK", "ACCESS_CONTROLLER_CHANNEL"})
_UNKNOWN_TYPE = "unknown"
_RSSI_LIMIT = 1000  # |dBm| beyond this is garbage, not a measurement
_NO_SGTIN = ""
_LAST = 1 << 30  # sort key for channel keys that are not integers
_KEY_WIDTH = 12

_Raw = Mapping[str, Any]
_Scope = Literal["room", "device", "valve", "contact"]


@dataclass(frozen=True, slots=True)
class ParseReport:
    """What the parser noticed besides the snapshot (for the sources to log once)."""

    collisions: tuple[str, ...] = ()  # base names that more than one entity wanted
    unmapped_models: tuple[str, ...] = ()  # raw model strings without a `device_models` entry


@dataclass(frozen=True, slots=True)
class _RoomInfo:
    group_id: str
    name: str
    raw: _Raw


@dataclass(frozen=True, slots=True)
class _DeviceInfo:
    device_id: str
    sgtin: str
    name: str
    room: str
    device_type: str
    channels: tuple[tuple[str, _Raw], ...]  # (channel key, channel), ordered by channel number


# --- value coercion --------------------------------------------------------------------------


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _rssi(value: object) -> int | None:
    number = _num(value)
    if number is None or not number.is_integer() or abs(number) > _RSSI_LIMIT:
        return None
    return int(number)


def _extra(value: object) -> float | str | bool | None:
    if isinstance(value, bool | str):
        return value
    return _num(value)


def _extras(config: ExtractConfig, scope: _Scope, source: _Raw) -> Extras:
    return MappingProxyType(
        {x.key: _extra(source.get(x.field)) for x in config.extras if x.scope == scope}
    )


def _read(
    source: _Raw, mapping: Mapping[str, str], attr: str, coerce: Callable[[object], Any]
) -> Any:
    field = mapping.get(attr)
    return None if field is None else coerce(source.get(field))


# --- naming ----------------------------------------------------------------------------------


def _assign_names(bases: list[str], keys: list[tuple[str, ...]]) -> tuple[list[str], set[str]]:
    """Unique names for `bases`; the first of a colliding group (by key) keeps the base name.

    Returns the names (same order as `bases`) and the set of colliding base names. Suffixes are
    `-2`, `-3`, ... and skip any name another entity already owns.
    """
    counts: dict[str, int] = {}
    for base in bases:
        counts[base] = counts.get(base, 0) + 1
    collided = {base for base, n in counts.items() if n > 1}
    used = {base for base in counts if base not in collided}
    seen: dict[str, int] = {}
    names = [""] * len(bases)
    for index in sorted(range(len(bases)), key=lambda i: keys[i]):
        base = bases[index]
        if base not in collided:
            names[index] = base
            continue
        n = seen.get(base, 0) + 1
        candidate = base if n == 1 else f"{base}-{n}"
        while candidate in used:
            n += 1
            candidate = f"{base}-{n}"
        seen[base] = n
        used.add(candidate)
        names[index] = candidate
    return names, collided


# --- structure -------------------------------------------------------------------------------


def _sections(raw: object) -> tuple[_Raw, _Raw]:
    if not isinstance(raw, dict):
        raise UpstreamError("configuration is not a JSON object")
    devices, groups = raw.get("devices"), raw.get("groups")
    if not isinstance(devices, dict) or not isinstance(groups, dict):
        raise UpstreamError("configuration has no devices or groups object")
    return devices, groups


def _rooms(groups: _Raw, config: ExtractConfig) -> tuple[list[_RoomInfo], set[str]]:
    found: list[tuple[str, str, _Raw]] = []
    for group_id, group in groups.items():
        if not isinstance(group, dict) or group.get("type") != config.room_group_type:
            continue
        label = group.get("label")
        if isinstance(label, str) and label.strip():
            found.append((str(group_id), label.strip(), group))
    names, collided = _assign_names([f[1] for f in found], [(f[0],) for f in found])
    return [_RoomInfo(f[0], n, f[2]) for f, n in zip(found, names, strict=True)], collided


def _device_rooms(groups: _Raw, rooms: list[_RoomInfo]) -> dict[str, set[str]]:
    """Device id -> ids of the room groups that list it in `channels[].deviceId`."""
    joined: dict[str, set[str]] = {}
    for room in rooms:
        channels = room.raw.get("channels")
        for channel in channels if isinstance(channels, list) else ():
            device_id = channel.get("deviceId") if isinstance(channel, dict) else None
            if isinstance(device_id, str):
                joined.setdefault(device_id, set()).add(room.group_id)
    return joined


def _channels(device: _Raw) -> tuple[tuple[str, _Raw], ...]:
    channels = device.get("functionalChannels")
    if not isinstance(channels, dict):
        return ()
    items = [(str(k), v) for k, v in channels.items() if isinstance(v, dict)]
    return tuple(sorted(items, key=lambda kv: (int(kv[0]) if kv[0].isdecimal() else _LAST, kv[0])))


def _base_channel(info: _DeviceInfo) -> _Raw:
    for _, channel in info.channels:
        ctype = channel.get("functionalChannelType")
        if isinstance(ctype, str) and (ctype.startswith(_BASE_PREFIX) or ctype in _BASE_TYPES):
            return channel
    return {}


def _device_type(device: _Raw, config: ExtractConfig, unmapped: list[str]) -> str:
    model = device.get("modelType")
    if not isinstance(model, str) or not model.strip():
        return _UNKNOWN_TYPE
    mapped = config.device_models.get(model)
    if mapped is not None:
        return mapped
    if model not in unmapped:
        unmapped.append(model)
    return model.strip().lower()


def _devices(
    devices: _Raw,
    config: ExtractConfig,
    rooms: list[_RoomInfo],
    joined: dict[str, set[str]],
) -> tuple[list[_DeviceInfo], set[str], list[str]]:
    room_name = {r.group_id: r.name for r in rooms}
    unmapped: list[str] = []
    drafts: list[tuple[str, str, str, str, _Raw]] = []
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            continue
        in_rooms = joined.get(str(device_id), set())
        room = room_name[next(iter(in_rooms))] if len(in_rooms) == 1 else config.system_room
        sgtin = device.get("serializedGlobalTradeItemNumber")
        drafts.append(
            (
                str(device_id),
                sgtin if isinstance(sgtin, str) else _NO_SGTIN,
                room,
                _device_type(device, config, unmapped),
                device,
            )
        )
    names, collided = _assign_names(
        [f"{room} {dtype}" for _, _, room, dtype, _ in drafts], [(d[1], d[0]) for d in drafts]
    )
    infos = [
        _DeviceInfo(did, sgtin, name, room, dtype, _channels(raw))
        for (did, sgtin, room, dtype, raw), name in zip(drafts, names, strict=True)
    ]
    return infos, collided, unmapped


def _build_device(info: _DeviceInfo, config: ExtractConfig) -> Device:
    base = _base_channel(info)
    flags = config.device_flags
    return Device(
        name=info.name,
        room=info.room,
        device_type=info.device_type,
        low_battery=_read(base, flags, "low_battery", _flag),
        unreachable=_read(base, flags, "unreachable", _flag),
        undervoltage=_read(base, flags, "undervoltage", _flag),
        rssi_dbm=_read(base, flags, "rssi_dbm", _rssi),
        extras=_extras(config, "device", base),
    )


def _build_room(room: _RoomInfo, config: ExtractConfig) -> Room:
    fields = config.rooms
    return Room(
        name=room.name,
        temperature_celsius=_read(room.raw, fields, "temperature_celsius", _num),
        setpoint_celsius=_read(room.raw, fields, "setpoint_celsius", _num),
        humidity=_read(room.raw, fields, "humidity", _num),
        control_mode=_read(room.raw, fields, "control_mode", _text),
        window_state=_read(room.raw, fields, "window_state", _text),
        extras=_extras(config, "room", room.raw),
    )


def _channel_room(channel: _Raw, rooms: list[_RoomInfo]) -> str | None:
    """The one room a channel's `groups` names; `None` if no room or more than one."""
    groups = channel.get("groups")
    if not isinstance(groups, list):
        return None
    wanted = {g for g in groups if isinstance(g, str)}
    names = {r.name for r in rooms if r.group_id in wanted}
    return next(iter(names)) if len(names) == 1 else None


@dataclass(frozen=True, slots=True)
class _Draft:
    """A valve or contact before its unique name is known."""

    room: str
    device_type: str
    base_name: str
    sort_key: tuple[str, ...]  # (sgtin, device id, channel number): stable, never exported
    channel: _Raw
    fields: Mapping[str, str]


def _sort_key(info: _DeviceInfo, channel_key: str) -> tuple[str, ...]:
    return (info.sgtin, info.device_id, channel_key.zfill(_KEY_WIDTH))


def _valve_drafts(
    infos: list[_DeviceInfo], rooms: list[_RoomInfo], config: ExtractConfig
) -> list[_Draft]:
    drafts: list[_Draft] = []
    for info in infos:
        for key, channel in info.channels:
            for rule in config.valves:
                if channel.get("functionalChannelType") != rule.channel_type:
                    continue
                if rule.room_from == "device_room":
                    room: str | None = info.room
                    base = info.name
                else:
                    room = _channel_room(channel, rooms)
                    base = f"{room} {rule.device_type}"
                if room is not None:
                    key_ = _sort_key(info, key)
                    drafts.append(_Draft(room, rule.device_type, base, key_, channel, rule.fields))
    return drafts


def _contact_drafts(infos: list[_DeviceInfo], config: ExtractConfig) -> list[_Draft]:
    return [
        _Draft(info.room, info.device_type, info.name, _sort_key(info, key), channel, rule.fields)
        for info in infos
        for key, channel in info.channels
        for rule in config.contacts
        if channel.get("functionalChannelType") == rule.channel_type
    ]


def _build_valves(drafts: list[_Draft], config: ExtractConfig) -> tuple[list[Valve], set[str]]:
    names, collided = _assign_names([d.base_name for d in drafts], [d.sort_key for d in drafts])
    return [
        Valve(
            room=d.room,
            device_type=d.device_type,
            device=name,
            position_ratio=_read(d.channel, d.fields, "position_ratio", _num),
            actual_temperature_celsius=_read(
                d.channel, d.fields, "actual_temperature_celsius", _num
            ),
            extras=_extras(config, "valve", d.channel),
        )
        for d, name in zip(drafts, names, strict=True)
    ], collided


def _build_contacts(drafts: list[_Draft], config: ExtractConfig) -> tuple[list[Contact], set[str]]:
    names, collided = _assign_names([d.base_name for d in drafts], [d.sort_key for d in drafts])
    return [
        Contact(
            room=d.room,
            device_type=d.device_type,
            device=name,
            window_state=_read(d.channel, d.fields, "window_state", _text),
            extras=_extras(config, "contact", d.channel),
        )
        for d, name in zip(drafts, names, strict=True)
    ], collided


def parse_with_report(
    raw: object,
    now: float,
    extract: ExtractConfig,
    on_collision: CollisionPolicy = "error",
) -> tuple[Snapshot, ParseReport]:
    """`parse_snapshot` plus what the parser noticed. Raises like `parse_snapshot`."""
    devices_raw, groups_raw = _sections(raw)
    rooms, collided = _rooms(groups_raw, extract)
    infos, device_collided, unmapped = _devices(
        devices_raw, extract, rooms, _device_rooms(groups_raw, rooms)
    )
    valves, valve_collided = _build_valves(_valve_drafts(infos, rooms, extract), extract)
    contacts, contact_collided = _build_contacts(_contact_drafts(infos, extract), extract)
    collided |= device_collided | valve_collided | contact_collided
    if collided and on_collision == "error":
        raise NameCollisionError(sorted(collided))
    snapshot = Snapshot(
        taken_at=now,
        rooms=tuple(_build_room(r, extract) for r in rooms),
        devices=tuple(_build_device(i, extract) for i in infos),
        valves=tuple(valves),
        contacts=tuple(contacts),
    )
    return snapshot, ParseReport(tuple(sorted(collided)), tuple(unmapped))


def parse_snapshot(
    raw: object,
    now: float,
    extract: ExtractConfig,
    on_collision: CollisionPolicy = "error",
) -> Snapshot:
    """Build a `Snapshot` from the raw configuration JSON (spec 4).

    `on_collision="error"` raises `NameCollisionError` when two devices, valves, contacts or rooms
    would get the same name; `"suffix"` appends `-2`, `-3` ordered by SGTIN. Raises
    `UpstreamError` only when `raw` is not a configuration object at all.
    """
    return parse_with_report(raw, now, extract, on_collision)[0]
