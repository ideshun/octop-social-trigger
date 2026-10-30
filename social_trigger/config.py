"""Strict configuration validation and deterministic scope resolution."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULTS = {
    "mode": "smart",
    "visibilityRequired": "all",
    "replyProbability": 0.25,
    "smartScoreThreshold": 0.7,
    "decisionModelEnabled": True,
    "decisionModelTimeoutMs": 1800,
    "decisionModelMaxCallsPerDay": 100,
    "cooldownSeconds": 180,
    "maxPassiveRepliesPerHour": 58,
    "maxPassiveRepliesPerDay": 580,
    "maxConsecutiveReplies": 2,
    "maxBotReplyRatio": 0.5,
    "randomDelayMinMs": 1000,
    "randomDelayMaxMs": 5000,
    "debounceMs": 1500,
    "contextMessages": 20,
    "contextTtlSeconds": 600,
    "mentionBypassCooldown": True,
    "quietHours": {"enabled": False, "start": "23:00", "end": "08:00"},
    "classifier": {"enabled": False, "timeoutMs": 1800, "maxCallsPerDay": 100},
}
TOP = {
    "enabled",
    "dryRun",
    "timezone",
    "defaults",
    "channelTypes",
    "channelInstances",
    "groups",
    "groupAgents",
    "allowGroups",
    "denyGroups",
}
MODES = {"disabled", "mention_only", "smart", "probability", "always"}
RANGES = {
    "replyProbability": (0, 1),
    "smartScoreThreshold": (0, 1),
    "decisionModelTimeoutMs": (0, 3000),
    "decisionModelMaxCallsPerDay": (0, 100000),
    "maxBotReplyRatio": (0, 1),
    "cooldownSeconds": (0, 86400),
    "maxPassiveRepliesPerHour": (0, 10000),
    "maxPassiveRepliesPerDay": (0, 100000),
    "maxConsecutiveReplies": (1, 100),
    "randomDelayMinMs": (0, 300000),
    "randomDelayMaxMs": (0, 300000),
    "debounceMs": (0, 60000),
    "contextMessages": (0, 100),
    "contextTtlSeconds": (1, 86400),
}


def _merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _policy(value, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected object")
    extra = value.keys() - DEFAULTS.keys()
    if extra:
        raise ValueError(f"{where}: unknown fields {sorted(extra)}")
    for key, val in value.items():
        if key in RANGES:
            lo, hi = RANGES[key]
            expected = (
                (int, float) if key in ("replyProbability", "smartScoreThreshold", "maxBotReplyRatio") else (int,)
            )
            if isinstance(val, bool) or not isinstance(val, expected) or not lo <= val <= hi:
                raise ValueError(f"{where}.{key}: expected {lo}..{hi}")
        elif key == "mode" and (not isinstance(val, str) or val not in MODES):
            raise ValueError(f"{where}.mode: invalid mode")
        elif key == "visibilityRequired" and val != "all":
            raise ValueError(f"{where}.visibilityRequired: only all is supported")
        elif key in ("mentionBypassCooldown", "decisionModelEnabled") and type(val) is not bool:
            raise ValueError(f"{where}.{key}: expected boolean")
        elif key in ("quietHours", "classifier"):
            allowed = DEFAULTS[key]
            if not isinstance(val, dict) or val.keys() - allowed.keys():
                raise ValueError(f"{where}.{key}: invalid object or fields")
            for sub, v in val.items():
                if sub == "enabled" and type(v) is not bool:
                    raise ValueError(f"{where}.{key}.enabled: expected boolean")
                if sub in ("start", "end") and (
                    not isinstance(v, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", v)
                ):
                    raise ValueError(f"{where}.{key}.{sub}: expected HH:MM")
                if sub in ("timeoutMs", "maxCallsPerDay") and (type(v) is not int or not 0 <= v <= 100000):
                    raise ValueError(f"{where}.{key}.{sub}: expected integer 0..100000")
            if key == "classifier" and val.get("enabled"):
                raise ValueError(f"{where}.classifier: classifier is not implemented")


def _table(value, depth, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected object")
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{where}: IDs must be nonempty strings")
        if depth == 1:
            _policy(item, f"{where}.{key}")
        else:
            _table(item, depth - 1, f"{where}.{key}")


def validate(raw):
    if not isinstance(raw, dict) or raw.keys() - TOP:
        raise ValueError("configuration must be an object with known fields")
    config = {
        "enabled": False,
        "dryRun": True,
        "timezone": "Asia/Shanghai",
        "defaults": {},
        "channelTypes": {},
        "channelInstances": {},
        "groups": {},
        "groupAgents": {},
        "allowGroups": [],
        "denyGroups": [],
    }
    config.update(copy.deepcopy(raw))
    for key in ("enabled", "dryRun"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key}: expected boolean")
    try:
        ZoneInfo(config["timezone"])
    except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("timezone: expected an installed IANA timezone") from exc
    _policy(config["defaults"], "defaults")
    config["defaults"] = _merge(DEFAULTS, config["defaults"])
    for key, depth in (("channelTypes", 1), ("channelInstances", 1), ("groups", 2), ("groupAgents", 3)):
        _table(config[key], depth, key)
    for key in ("allowGroups", "denyGroups"):
        groups = config[key]
        if not isinstance(groups, list) or any(
            not isinstance(x, list) or len(x) != 2 or any(not isinstance(i, str) or not i.strip() for i in x)
            for x in groups
        ):
            raise ValueError(f"{key}: expected list of [channelInstanceId, groupId]")

    # Validate combined settings as well as individual overrides.
    def check_merged(p):
        if p["randomDelayMinMs"] > p["randomDelayMaxMs"]:
            raise ValueError("randomDelayMinMs must not exceed randomDelayMaxMs")

    check_merged(config["defaults"])
    return config


def load(path):
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))


def effective(config, platform, instance, group, agent):
    policy = copy.deepcopy(config["defaults"])
    source = {key: "defaults" for key in policy}
    for name, patch in (
        ("channelTypes", config["channelTypes"].get(platform, {})),
        ("channelInstances", config["channelInstances"].get(instance, {})),
        ("groups", config["groups"].get(instance, {}).get(group, {})),
        ("groupAgents", config["groupAgents"].get(instance, {}).get(group, {}).get(agent, {})),
    ):
        policy = _merge(policy, patch)
        source.update({key: name for key in patch})
    if policy["randomDelayMinMs"] > policy["randomDelayMaxMs"]:
        raise ValueError("effective randomDelayMinMs exceeds randomDelayMaxMs")
    return policy, source
