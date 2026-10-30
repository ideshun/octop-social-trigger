"""Exercise the actual Octo inbox through the shared Gateway policy hook."""

import asyncio
import time
from unittest.mock import AsyncMock

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
async def test_octo_passive_input_releases_inbox_and_selected_reply_is_delivered(tmp_path, dry_run, probability):
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
