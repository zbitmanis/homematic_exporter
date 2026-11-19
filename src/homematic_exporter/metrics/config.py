"""`config.yaml` loading and validation (spec 5.1, R19-R21).

`load_config` resolves the file (R21), reads it with hard limits, parses it with a strict
`yaml.SafeLoader` (no aliases, no duplicate keys) and validates it into `AppConfig`. It never reads
the environment: `app` passes `CONFIG_FILE` as `path`.
"""

import logging
import os
import stat
from collections.abc import Hashable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from homematic_exporter.config_models import ExtractConfig, Tuning
from homematic_exporter.metrics.schema import (
    MAX_METRICS,
    ConfigError,
    Issue,
    MetricDef,
    quote,
    validate_metrics,
)

logger = logging.getLogger(__name__)

MOUNT_CONFIG_PATH = Path("/etc/homematic-exporter/config/config.yaml")
IMAGE_CONFIG_PATH = Path("/app/default-config.yaml")
# Used when running from a checkout (tests, `uvicorn` in the repo) instead of the image.
CHECKOUT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "default-config.yaml"

MAX_CONFIG_BYTES = 1024 * 1024
MAX_RETENTION_DAYS = 36500  # 100 years; `timedelta` overflows far above this
MAX_PATH_PART = 40

__all__ = ["AppConfig", "ConfigError", "load_config", "parse_config"]


class AppConfig(BaseModel):
    """The whole `config.yaml`: `tuning`, `extract` (shared models) and the metric definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    tuning: Tuning = Field(default_factory=Tuning)
    extract: ExtractConfig
    metrics: tuple[MetricDef, ...] = Field(max_length=MAX_METRICS)


class _StrictLoader(yaml.SafeLoader):
    """`SafeLoader` without aliases (anchor bombs) and without duplicate mapping keys."""

    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        if self.check_event(yaml.AliasEvent):
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "aliases are not allowed",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, Hashable):
                continue  # the parent class rejects it with a proper error
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {quote(key)}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _parse_yaml(text: str) -> object:
    loader: _StrictLoader | None = None
    try:
        loader = _StrictLoader(text)  # the constructor already rejects unreadable characters
        return loader.get_single_data()
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f"line {mark.line + 1}: " if mark is not None else ""
        raise ConfigError([Issue("", f"{where}{exc.problem or 'invalid YAML'}")]) from None
    except yaml.YAMLError:
        raise ConfigError([Issue("", "invalid YAML (unreadable characters)")]) from None
    except RecursionError:
        raise ConfigError([Issue("", "YAML is nested too deeply")]) from None
    except ValueError:  # e.g. an integer literal beyond Python's digit limit
        raise ConfigError([Issue("", "invalid YAML (unusable number)")]) from None
    finally:
        if loader is not None:
            loader.dispose()


def _issue_path(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + part[:MAX_PATH_PART]
    return out


def _pydantic_issues(exc: ValidationError) -> list[Issue]:
    issues: list[Issue] = []
    for err in exc.errors(include_input=False, include_url=False):
        if err["type"] == "extra_forbidden":
            message = "unknown key"
        elif err["type"] == "missing":
            message = "missing required key"
        else:
            message = err["msg"].removeprefix("Value error, ")
        issues.append(Issue(_issue_path(err["loc"]), message))
    return issues


def parse_config(raw: object) -> AppConfig:
    """Validate parsed YAML into `AppConfig`; raises `ConfigError` with key paths (R19)."""
    if not isinstance(raw, dict):
        raise ConfigError([Issue("", "the top level of the config must be a mapping")])
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_pydantic_issues(exc)) from None
    extras = {(e.scope, e.key) for e in config.extract.extras}
    issues = validate_metrics(config.metrics, extras)
    if config.tuning.state_retention_days > MAX_RETENTION_DAYS:
        issues.append(Issue("tuning.state_retention_days", f"must be at most {MAX_RETENTION_DAYS}"))
    if issues:
        raise ConfigError(issues)
    return config


def _read_text(path: Path) -> str:
    """Read a regular file of bounded size; symlinks are followed (ConfigMap mounts use them)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)  # non-blocking: a FIFO must not hang
    except FileNotFoundError:
        raise ConfigError([Issue("", "config file not found")]) from None
    except OSError as exc:
        raise ConfigError([Issue("", f"cannot open config file ({exc.strerror})")]) from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ConfigError([Issue("", "config path is not a regular file")])
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise ConfigError([Issue("", f"cannot read config file ({exc.strerror})")]) from None
    finally:
        os.close(fd)
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigError([Issue("", f"config file is too large (limit {MAX_CONFIG_BYTES} bytes)")])
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError([Issue("", "config file is not valid UTF-8")]) from None


def _resolve(path: Path | None) -> tuple[Path, str]:
    if path is not None:
        return path, "explicit path"
    if MOUNT_CONFIG_PATH.exists():
        return MOUNT_CONFIG_PATH, "mounted config"
    for bundled in (IMAGE_CONFIG_PATH, CHECKOUT_CONFIG_PATH):
        if bundled.exists():
            return bundled, "bundled default"
    raise ConfigError([Issue("", "no config file: nothing mounted and no bundled default")])


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate the config (R21).

    An explicit `path` must exist. With `None`: the mount path if present, else the bundled
    default. A broken file fails; there is no fallback to the default after a bad mount.
    """
    chosen, origin = _resolve(path)
    logger.info("loading config from %s (%s)", chosen, origin)
    try:
        return parse_config(_parse_yaml(_read_text(chosen)))
    except ConfigError as exc:
        raise ConfigError(exc.issues, source=str(chosen)) from None
