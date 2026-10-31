"""Exercise the actual Octo inbox through the shared Gateway policy hook."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from social_trigger.config import instance_key, validate
from social_trigger.runtime import Runtime

from octop_gateway.manager import ChannelManager
from octop_gateway.models import MessageEvent

Octo = pytest.importorskip("octo_channel_impl.channel")
Inbox = pytest.importorskip("octo_channel_impl.state").Inbox


async def until(predicate):
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run,probability", [(True, 1), (False, 0), (False, 1)])
@pytest.mark.parametrize("require_mention", [False, True])
async def test_octo_passive_input_releases_inbox_and_selected_reply_is_delivered(
    tmp_path, dry_run, probability, require_mention
):
    calls = []

    async def process(message):
        calls.append(message)
        yield MessageEvent.text("reply")
        yield MessageEvent.completed()

    channel = Octo.OctoChannel(
        process,
        channel_id="instance",
        tenant_id="expert",
        config=Octo.OctoConfig(show_typing=False, require_mention=require_mention, state_dir=str(tmp_path / "inbox")),
    )
    channel._inbox = Inbox(tmp_path / "inbox" / "inbox.sqlite")
    channel._robot_id = "bot"
    channel._owner_uid = "owner"
    channel.start = AsyncMock()
    channel._lookup_member_name = lambda *_: "Human"
    channel._backfill_history = AsyncMock()
    channel.resolve_sender_is_bot = AsyncMock(return_value=False)
    channel._send_text = AsyncMock()
    config = validate(
        {
            "schemaVersion": 2,
            "enabled": True,
            "dryRun": dry_run,
            "allowGroups": [[instance_key("octo", "instance"), "group"]],
            "defaults": {
                "mode": "probability",
                "replyProbability": probability,
                "cooldownSeconds": 0,
                "maxBotReplyRatio": 1,
                "debounceMs": 5,
                "randomDelayMinMs": 0,
                "randomDelayMaxMs": 0,
            },
        }
    )
    runtime = Runtime(config, tmp_path / "policy.db")
    manager = ChannelManager({"instance": channel}, inbound_handler=runtime.handle)
    await manager.start()
    channel._dispatch_task = asyncio.create_task(channel._dispatch_loop())
    try:
        for ident in range(40):
            channel._accept_message(
                {
                    "message_id": str(ident),
                    "from_uid": "human",
                    "channel_id": "group",
                    "channel_type": 2,
                    "timestamp": time.time(),
                    "payload": {"type": 1, "content": "hello"},
                },
                via="ws",
            )
            await until(lambda: channel._inbox.stats()["pending"] == 0)
        await until(lambda: not runtime._tasks)
        assert not channel._scheduled
        if dry_run or not probability:
            assert calls == []
            channel._send_text.assert_not_awaited()
        else:
            assert calls
            assert channel._send_text.await_count == len(calls)
        # Native @ replies still work with the plugin and mention gating enabled.
        before = len(calls)
        channel._accept_message(
            {
                "message_id": "mention",
                "from_uid": "human",
                "channel_id": "group",
                "channel_type": 2,
                "timestamp": time.time(),
                "payload": {"type": 1, "content": "@bot hi", "mention": {"uids": ["bot"]}},
            },
            via="ws",
        )
        await until(lambda: len(calls) == before + 1)
    finally:
        await runtime.wait_closed()
        await manager.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
async def test_octo_member_classification_is_cached_and_unknown_is_not_human(tmp_path, monkeypatch, wrapped):
    channel = Octo.OctoChannel(AsyncMock(), channel_id="instance", config=Octo.OctoConfig())
    from unittest.mock import Mock

    members = [{"uid": "human", "name": "Name", "robot": 0}, {"uid": "bot", "robot": 1}]
    fetch = Mock(return_value={"members": members} if wrapped else members)
    monkeypatch.setattr(Octo.octo_api, "octo_request", fetch)
    for uid, expected in (("human", False), ("bot", True), ("missing", None)):
        message = channel.parse_inbound(
            {
                "from_uid": uid,
                "channel_id": "group",
                "channel_type": 2,
                "is_group": True,
                "text": "hello",
                "bot_mentioned": False,
            }
        )
        assert await channel.resolve_sender_is_bot(message) is expected
    assert fetch.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sender_is_bot,claimed,reason",
    [(True, True, "bot_message"), (False, False, None), (None, True, "sender_identity_unknown")],
)
async def test_octo_mention_checks_sender_before_native_routing(tmp_path, sender_is_bot, claimed, reason):
    channel = Octo.OctoChannel(AsyncMock(), channel_id="instance", tenant_id="expert", config=Octo.OctoConfig())
    channel._robot_id = "bot"
    channel.resolve_sender_is_bot = AsyncMock(return_value=sender_is_bot)
    message = channel.parse_inbound(
        {
            "from_uid": "sender",
            "channel_id": "group",
            "channel_type": 2,
            "is_group": True,
            "text": "hello",
            "bot_mentioned": True,
        }
    )
    runtime = Runtime(
        validate({"schemaVersion": 2, "enabled": True, "allowGroups": [[instance_key("octo", "instance"), "group"]]}),
        tmp_path / "policy.db",
    )
    try:
        assert await runtime.handle(channel, message, AsyncMock()) is claimed
        channel.resolve_sender_is_bot.assert_awaited_once()
        if reason:
            assert runtime.recent[-1]["reasonCode"] == reason
    finally:
        await runtime.wait_closed()


@pytest.mark.asyncio
async def test_known_bot_is_blocked_outside_selected_group(tmp_path):
    channel = Octo.OctoChannel(AsyncMock(), channel_id="instance", tenant_id="expert", config=Octo.OctoConfig())
    channel.resolve_sender_is_bot = AsyncMock(return_value=True)
    message = channel.parse_inbound(
        {
            "from_uid": "other-bot",
            "channel_id": "other",
            "channel_type": 2,
            "is_group": True,
            "text": "hello",
            "bot_mentioned": True,
        }
    )
    runtime = Runtime(validate({"schemaVersion": 2, "enabled": True}), tmp_path / "policy.db")
    try:
        assert await runtime.handle(channel, message, AsyncMock()) is True
        assert runtime.recent[-1]["reasonCode"] == "bot_message"
    finally:
        await runtime.wait_closed()


@pytest.mark.asyncio
async def test_unselected_octo_group_does_not_fall_back_to_replying_to_every_message(tmp_path):
    calls = []
    answer = "（不回复）"

    async def process(message):
        calls.append(message)
        yield MessageEvent.text(answer)
        yield MessageEvent.completed()

    channel = Octo.OctoChannel(
        process,
        channel_id="instance",
        tenant_id="expert",
        config=Octo.OctoConfig(require_mention=False, show_typing=False, state_dir=str(tmp_path / "inbox")),
    )
    channel._inbox = Inbox(tmp_path / "inbox" / "inbox.sqlite")
    channel._robot_id = "bot"
    channel.start = AsyncMock()
    channel.resolve_sender_is_bot = AsyncMock(return_value=False)
    channel._lookup_member_name = lambda *_: "Human"
    channel._backfill_history = AsyncMock()
    channel._send_text = AsyncMock()
    config = validate(
        {
            "schemaVersion": 2,
            "enabled": True,
            "dryRun": False,
            "allowGroups": [[instance_key("qq", "*"), "*"]],
            "defaults": {"mode": "probability", "replyProbability": 0, "debounceMs": 5},
        }
    )
    runtime = Runtime(config, tmp_path / "policy.db", config_path=tmp_path / "config.json")
    manager = ChannelManager({"instance": channel}, inbound_handler=runtime.handle)
    await manager.start()
    channel._dispatch_task = asyncio.create_task(channel._dispatch_loop())

    def send(ident, content, mention=False):
        channel._accept_message(
            {
                "message_id": ident,
                "from_uid": "human",
                "channel_id": "group",
                "channel_type": 2,
                "timestamp": time.time(),
                "payload": {"type": 1, "content": content, "mention": {"uids": ["bot"]} if mention else {}},
            },
            via="ws",
        )

    try:
        send("1", "ordinary")
        await until(lambda: any(r["reasonCode"] == "group_not_allowed" for r in runtime.recent))
        assert calls == []
        send("2", "@bot hello", mention=True)
        await until(lambda: len(calls) == 1)
        await until(lambda: any(r["reasonCode"] == "silent_output" for r in runtime.recent))
        channel._send_text.assert_not_awaited()

        answer = "reply"
        send("2b", "@bot hello", mention=True)
        await until(lambda: channel._send_text.await_count == 1)

        await runtime.update_settings(platform="octo", channel_id="instance", group_id="group", scope="groups")
        send("3", "ordinary")
        await until(lambda: any(r["reasonCode"] == "probability" for r in runtime.recent))
        assert len(calls) == 2
    finally:
        await runtime.wait_closed()
        await manager.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["mention", "sender"])
async def test_selected_group_does_not_fall_back_to_native_always_when_metadata_is_missing(tmp_path, missing):
    channel = Octo.OctoChannel(
        AsyncMock(), channel_id="instance", tenant_id="expert", config=Octo.OctoConfig(require_mention=False)
    )
    channel.resolve_sender_is_bot = AsyncMock(return_value=False) if missing == "mention" else None
    message = channel.parse_inbound(
        {
            "from_uid": "sender",
            "channel_id": "group",
            "channel_type": 2,
            "is_group": True,
            "text": "hello",
            "bot_mentioned": False,
        }
    )
    if missing == "mention":
        message.metadata.pop("bot_mentioned")
    runtime = Runtime(
        validate({"schemaVersion": 2, "enabled": True, "allowGroups": [[instance_key("octo", "instance"), "group"]]}),
        tmp_path / "policy.db",
    )
    try:
        assert await runtime.handle(channel, message, AsyncMock()) is True
        assert runtime.recent[-1]["reasonCode"] == (
            "unsupported_channel" if missing == "mention" else "sender_identity_unknown"
        )
    finally:
        await runtime.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,will_send", [("reply", True), ("（不回复）", False)])
async def test_octo_automatic_reply_respects_channel_history_limit(tmp_path, answer, will_send):
    calls = []

    async def process(message):
        calls.append(message)
        yield MessageEvent.text(answer)
        yield MessageEvent.completed()

    channel = Octo.OctoChannel(
        process,
        channel_id="instance",
        tenant_id="expert",
        config=Octo.OctoConfig(show_typing=False, history_limit=2, state_dir=str(tmp_path / "inbox")),
    )
    channel._inbox = Inbox(tmp_path / "inbox" / "inbox.sqlite")
    channel._robot_id = "bot"
    channel.start = AsyncMock()
    channel.resolve_sender_is_bot = AsyncMock(return_value=False)
    channel._lookup_member_name = lambda *_: "Human"
    channel._send_text = AsyncMock()
    runtime = Runtime(
        validate(
            {
                "schemaVersion": 2,
                "enabled": True,
                "dryRun": False,
                "allowGroups": [[instance_key("octo", "instance"), "group"]],
                "defaults": {
                    "mode": "probability",
                    "replyProbability": 1,
                    "cooldownSeconds": 0,
                    "maxBotReplyRatio": 1,
                    "debounceMs": 100,
                    "randomDelayMinMs": 0,
                    "randomDelayMaxMs": 0,
                    "contextMessages": 20,
                },
            }
        ),
        tmp_path / "policy.db",
    )
    manager = ChannelManager({"instance": channel}, inbound_handler=runtime.handle)
    await manager.start()
    channel._dispatch_task = asyncio.create_task(channel._dispatch_loop())
    try:
        for ident in range(5):
            channel._accept_message(
                {
                    "message_id": str(ident),
                    "from_uid": "human",
                    "channel_id": "group",
                    "channel_type": 2,
                    "timestamp": time.time(),
                    "payload": {"type": 1, "content": f"message {ident}"},
                },
                via="ws",
            )
        await until(lambda: len(calls) == 1)
        await until(lambda: not runtime._tasks)
        assert calls[0].text == "message 4"
        assert [item.text for item in calls[0].group_context.messages] == ["message 2", "message 3"]
        assert calls[0].metadata["social_trigger_auto"] is True
        assert channel._send_text.await_count == int(will_send)
    finally:
        await runtime.wait_closed()
        await manager.stop()


@pytest.mark.asyncio
async def test_octo_blocked_ordinary_and_mention_leave_inbox_without_model_call(tmp_path):
    calls = []

    async def process(message):
        calls.append(message)
        yield MessageEvent.text("reply")
        yield MessageEvent.completed()

    channel = Octo.OctoChannel(
        process,
        channel_id="instance",
        tenant_id="expert",
        config=Octo.OctoConfig(show_typing=False, state_dir=str(tmp_path / "inbox")),
    )
    channel._inbox = Inbox(tmp_path / "inbox" / "inbox.sqlite")
    channel._robot_id = "bot"
    channel.start = AsyncMock()
    channel._lookup_member_name = lambda *_: "Human"
    channel._backfill_history = AsyncMock()
    channel.resolve_sender_is_bot = AsyncMock(return_value=False)
    channel._send_text = AsyncMock()
    runtime = Runtime(
        validate(
            {
                "schemaVersion": 2,
                "enabled": True,
                "dryRun": False,
                "allowGroups": [[instance_key("octo", "instance"), "group"]],
                "defaults": {"blockedTerms": ["forbidden"], "mode": "always", "debounceMs": 0},
            }
        ),
        tmp_path / "policy.db",
    )
    provider = AsyncMock()
    runtime.bind_decision_scorer(provider)
    manager = ChannelManager({"instance": channel}, inbound_handler=runtime.handle)
    await manager.start()
    channel._dispatch_task = asyncio.create_task(channel._dispatch_loop())
    try:
        for ident, mention in (("ordinary", False), ("mention", True)):
            channel._accept_message(
                {
                    "message_id": ident,
                    "from_uid": "human",
                    "channel_id": "group",
                    "channel_type": 2,
                    "timestamp": time.time(),
                    "payload": {
                        "type": 1,
                        "content": "FORBIDDEN",
                        **({"mention": {"uids": ["bot"]}} if mention else {}),
                    },
                },
                via="ws",
            )
        await until(lambda: sum(item["reasonCode"] == "blocked_term" for item in runtime.recent) == 2)
        await until(lambda: channel._inbox.stats()["pending"] == 0)
        assert calls == []
        provider.assert_not_awaited()
        channel._send_text.assert_not_awaited()
    finally:
        await runtime.wait_closed()
        await manager.stop()


@pytest.mark.asyncio
async def test_configured_filter_does_not_let_mentions_bypass_old_gateway(tmp_path):
    channel = Octo.OctoChannel(AsyncMock(), channel_id="instance", tenant_id="expert", config=Octo.OctoConfig())
    message = channel.parse_inbound(
        {
            "from_uid": "human",
            "channel_id": "group",
            "channel_type": 2,
            "is_group": True,
            "text": "safe message",
            "bot_mentioned": True,
        }
    )
    runtime = Runtime(
        validate({"schemaVersion": 2, "enabled": True, "defaults": {"blockedTerms": ["restricted"]}}),
        tmp_path / "policy.db",
    )
    try:
        with patch("octop_gateway.channel.current_inbound_receipt", return_value=None):
            assert await runtime.handle(channel, message, AsyncMock()) is True
        assert runtime.recent[-1]["reasonCode"] == "input_filter_unavailable"
    finally:
        await runtime.wait_closed()
