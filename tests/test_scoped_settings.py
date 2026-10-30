"""Policy inheritance, namespace isolation and v1 migration behavior."""

import json
import sqlite3

import pytest

from social_trigger.config import DEFAULTS, effective, group_allowed, instance_key, validate
from social_trigger.core import Engine, Message
from social_trigger.runtime import Runtime


@pytest.mark.asyncio
async def test_inheritance_saves_only_differences_and_reset_keeps_other_scopes(tmp_path):
    runtime = Runtime(validate({"schemaVersion": 2}), tmp_path / "state.db", config_path=tmp_path / "config.json")
    await runtime.update_settings(enabled=True, scope="defaults", policy={"cooldownSeconds": 250})
    assert not group_allowed(runtime.config, "qq", "same", "same")
    assert not group_allowed(runtime.config, "octo", "same", "same")
    await runtime.update_settings(
        platform="octo", channel_id="same", scope="channelInstances", policy={"replyProbability": 0.8}
    )
    await runtime.update_settings(
        platform="octo", channel_id="same", group_id="same", scope="groups", policy={"cooldownSeconds": 60}
    )
    assert runtime.config["groups"][instance_key("octo", "same")]["same"] == {"cooldownSeconds": 60}
    assert group_allowed(runtime.config, "octo", "same", "same")
    assert not group_allowed(runtime.config, "qq", "same", "same")
    selected = runtime.settings_for("same", "same", "expert", platform="octo", scope="groups")
    assert selected["policy"]["replyProbability"] == 0.8
    assert selected["policySource"]["replyProbability"] == "channelInstances"
    assert selected["inheritedPolicy"]["cooldownSeconds"] == 250
    await runtime.update_settings(
        platform="octo",
        channel_id="same",
        group_id="same",
        agent_id="expert",
        scope="groupAgents",
        policy={"mode": "mention_only"},
    )
    await runtime.update_settings(platform="octo", channel_id="same", group_id="same", scope="groups", reset=True)
    actual, source = effective(runtime.config, "octo", "same", "same", "expert")
    assert actual["cooldownSeconds"] == 250
    assert actual["mode"] == "mention_only"
    assert source["mode"] == "groupAgents"
    assert json.loads(runtime.config_path.read_text())["schemaVersion"] == 2
    await runtime.wait_closed()


@pytest.mark.asyncio
async def test_nested_overrides_keep_inherited_values_and_invalid_parent_is_not_saved(tmp_path):
    runtime = Runtime(validate({"schemaVersion": 2}), tmp_path / "state.db", config_path=tmp_path / "config.json")
    await runtime.update_settings(
        platform="octo",
        channel_id="bot",
        group_id="group",
        scope="groups",
        policy={"quietHours": {"enabled": True}, "randomDelayMaxMs": 1500},
    )
    policy = runtime.settings_for("bot", "group", platform="octo", scope="groups")["policy"]
    assert policy["quietHours"] == {"enabled": True, "start": "23:00", "end": "08:00"}
    assert runtime.config["groups"][instance_key("octo", "bot")]["group"]["quietHours"] == {"enabled": True}
    await runtime.update_settings(scope="defaults", policy={"quietHours": {"start": "22:30"}})
    policy = runtime.settings_for("bot", "group", platform="octo", scope="groups")["policy"]
    assert policy["quietHours"]["start"] == "22:30"
    saved = runtime.config_path.read_text()
    with pytest.raises(ValueError, match="randomDelayMinMs"):
        await runtime.update_settings(scope="defaults", policy={"randomDelayMinMs": 2000})
    assert runtime.config_path.read_text() == saved
    assert runtime.config["defaults"]["randomDelayMinMs"] == 1000
    await runtime.wait_closed()


def test_legacy_qq_policy_and_allowlist_migrate_without_enabling_other_platforms():
    config = validate({"enabled": True, "groups": {"same": {"same": {"cooldownSeconds": 12}}}})
    assert effective(config, "qq", "same", "same", "expert")[0]["cooldownSeconds"] == 12
    assert effective(config, "octo", "same", "same", "expert")[0]["cooldownSeconds"] == DEFAULTS["cooldownSeconds"]
    assert group_allowed(config, "qq", "new-instance", "new-group")
    assert not group_allowed(config, "octo", "same", "same")
    assert validate(config) == config


def test_legacy_quota_and_uncertain_reservation_survive_upgrade(tmp_path):
    database = tmp_path / "state.db"
    config = validate({"enabled": True, "dryRun": False})
    Engine(config, database)
    old = json.dumps(["tenant", "same", "same", "expert"], separators=(",", ":"))
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO replies VALUES ('pending', ?, 1000, 'pending')", (old,))
    engine = Engine(config, database, clock=lambda: 1001)
    msg = Message(
        platform="qq",
        tenantId="tenant",
        channelInstanceId="same",
        groupId="same",
        agentId="expert",
        messageId="message",
        senderId="human",
        text="hello",
        receivedAt=1001,
        visibilityGranted="all",
    )
    assert engine.evaluate(msg).reasonCode == "cooldown"
    with engine._connect() as db:
        assert db.execute("SELECT scope FROM replies").fetchone()[0] == engine._identity(msg)[0]
    other = Message(**{**msg.__dict__, "platform": "octo"})
    assert engine._identity(other)[0] != engine._identity(msg)[0]
