"""Build a reproducible native plugin archive; never packages local state."""

from pathlib import Path
import hashlib
import json
import tomllib
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from social_trigger.config import DEFAULTS, MODES, RANGES, validate  # noqa: E402

VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def schema():
    properties = {}
    for key, value in DEFAULTS.items():
        item = {"default": value}
        if key == "blockedTerms":
            item.update(type="array", maxItems=5000, items={"type": "string", "minLength": 1, "maxLength": 100})
        elif key == "mode":
            item.update(type="string", enum=sorted(MODES))
        elif key == "visibilityRequired":
            item.update(type="string", const="all")
        elif key in RANGES:
            lo, hi = RANGES[key]
            item.update(
                type="number" if key in ("replyProbability", "smartScoreThreshold", "maxBotReplyRatio") else "integer",
                minimum=lo,
                maximum=hi,
            )
        elif isinstance(value, bool):
            item.update(type="boolean")
        elif key == "quietHours":
            item.update(
                type="object",
                additionalProperties=False,
                properties={
                    "enabled": {"type": "boolean"},
                    "start": {"type": "string", "pattern": r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"},
                    "end": {"type": "string", "pattern": r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"},
                },
            )
        elif key == "classifier":
            item.update(
                type="object",
                additionalProperties=False,
                properties={
                    "enabled": {"type": "boolean", "const": False},
                    "timeoutMs": {"type": "integer", "minimum": 0, "maximum": 100000},
                    "maxCallsPerDay": {"type": "integer", "minimum": 0, "maximum": 100000},
                },
            )
        properties[key] = item
    scope = {"type": "object", "additionalProperties": {"$ref": "#/$defs/policy"}}
    pair = {
        "type": "array",
        "items": {
            "type": "array",
            "prefixItems": [{"type": "string", "minLength": 1}, {"type": "string", "minLength": 1}],
            "items": False,
            "minItems": 2,
            "maxItems": 2,
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "$defs": {"policy": {"type": "object", "properties": properties, "additionalProperties": False}},
        "properties": {
            "schemaVersion": {"type": "integer", "const": 2},
            "enabled": {"type": "boolean", "default": False},
            "dryRun": {"type": "boolean", "default": True},
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
            "defaults": {"$ref": "#/$defs/policy"},
            "channelTypes": scope,
            "channelInstances": scope,
            "groups": {"type": "object", "additionalProperties": scope},
            "groupAgents": {
                "type": "object",
                "additionalProperties": {"type": "object", "additionalProperties": scope},
            },
            "allowGroups": pair,
            "denyGroups": pair,
        },
    }


def archive(target, paths, prefix):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(paths):
            info = zipfile.ZipInfo(prefix + "/" + path.relative_to(ROOT).as_posix(), (2026, 10, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes())


def main():
    validate(json.loads((ROOT / "config.json").read_text()))
    if json.loads((ROOT / "config.json").read_text()).get("enabled") is not False:
        raise SystemExit("release config.json must explicitly disable triggering")
    (ROOT / "config.schema.json").write_text(json.dumps(schema(), ensure_ascii=False, indent=2) + "\n")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    files = [
        ROOT / name
        for name in (
            "main.py",
            "plugin.yaml",
            "icon.png",
            "config.json",
            "config.example.json",
            "config.schema.json",
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
        )
    ]
    files += list((ROOT / "social_trigger").glob("*.py"))
    files += list((ROOT / "docs").glob("*.md"))
    plugin = dist / f"octop-social-trigger-{VERSION}.zip"
    archive(plugin, files, "octop-social-trigger")
    (dist / "SHA256SUMS").write_text(hashlib.sha256(plugin.read_bytes()).hexdigest() + "  " + plugin.name + "\n")
    print((dist / "SHA256SUMS").read_text(), end="")


if __name__ == "__main__":
    main()
