"""Plugin-owned settings catalog, validation and scoped persistence."""

from __future__ import annotations

import copy

from .config import DEFAULTS, SCOPES
from .prompts import group_prompt_defaults


def _catalog(context):
    channels = copy.deepcopy(context.get("channels", []))
    groups = copy.deepcopy(context.get("groups", []))
    for group in groups:
        switches = group.pop("pluginSettings", {})
        group["channelParticipationEnabled"] = switches.get("social_trigger_enabled", True) is True
    return channels, groups


async def read_settings(runtime, context):
    channels, groups = _catalog(context)
    for group in groups:
        args = (group["channelId"], group["groupId"], group["agentId"])
        group["settings"] = runtime.settings_for(*args, platform=group["channelKind"], scope="groups")
        group["agentSettings"] = runtime.settings_for(*args, platform=group["channelKind"], scope="groupAgents")
    for channel in channels:
        channel["settings"] = runtime.settings_for(
            channel["channelId"], platform=channel["channelKind"], scope="channelInstances"
        )
    kinds = sorted({item["channelKind"] for item in [*channels, *groups]})
    return {
        "enabled": runtime.config["enabled"],
        "dryRun": runtime.config["dryRun"],
        "timezone": runtime.config["timezone"],
        "decisionModelSupported": True,
        "decisionModelConfigured": context.get("decisionModelConfigured"),
        "promptSettingsSupported": True,
        "promptDefaults": {"zh": group_prompt_defaults("zh"), "en": group_prompt_defaults("en")},
        "recent": list(runtime.recent)[-1] if runtime.recent else None,
        "groups": groups,
        "channels": channels,
        "defaults": runtime.settings_for(scope="defaults"),
        "channelTypes": [
            {"channelKind": kind, "settings": runtime.settings_for(platform=kind, scope="channelTypes")}
            for kind in kinds
        ],
    }


async def save_settings(runtime, context, values):
    selectors = {"enabled", "dryRun", "channelKind", "channelId", "groupId", "agentId", "scope", "reset"}
    if not isinstance(values, dict) or values.keys() - selectors - DEFAULTS.keys():
        raise ValueError("Unknown settings fields")
    for key in ("channelKind", "channelId", "groupId", "agentId", "scope"):
        if key in values and (not isinstance(values[key], str) or len(values[key]) > 1000):
            raise ValueError(f"{key}: expected a stable ID or scope")
    for key in ("enabled", "dryRun", "reset"):
        if key in values and type(values[key]) is not bool:
            raise ValueError(f"{key}: expected boolean")
    scope = values.get("scope", "groupAgents")
    if scope not in SCOPES:
        raise ValueError("Invalid settings scope")
    kind = values.get("channelKind", "qq")
    channel_id, group_id, agent_id = (values.get(key, "") for key in ("channelId", "groupId", "agentId"))
    channels, groups = _catalog(context)
    group = next(
        (
            item
            for item in groups
            if item["channelKind"] == kind
            and item["channelId"] == channel_id
            and item["groupId"] == group_id
            and (not agent_id or item["agentId"] == agent_id)
        ),
        None,
    )
    if scope in ("groups", "groupAgents") and group is None:
        raise LookupError("未找到该群聊，请先在群里与机器人对话")
    if scope == "channelInstances" and not any(
        item["channelKind"] == kind and item["channelId"] == channel_id for item in channels
    ):
        raise LookupError("未找到该通道")
    if scope == "channelTypes" and not any(item["channelKind"] == kind for item in channels):
        raise LookupError("未找到该通道类型")
    await runtime.update_settings(
        enabled=values.get("enabled"),
        dry_run=values.get("dryRun"),
        platform=kind,
        channel_id=channel_id,
        group_id=group_id,
        agent_id=group["agentId"] if group else agent_id,
        scope=scope,
        reset=values.get("reset", False),
        policy={key: value for key, value in values.items() if key not in selectors},
    )
