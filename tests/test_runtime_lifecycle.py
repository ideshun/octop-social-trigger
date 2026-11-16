"""Dispatch lifecycle checks without a real channel or decision endpoint."""

import asyncio
import gc
from types import SimpleNamespace

import pytest

from social_trigger.config import instance_key, validate
from social_trigger.runtime import Runtime

models = pytest.importorskip("octop_gateway.models")


@pytest.mark.asyncio
async def test_new_chatter_waits_for_active_dispatch_and_unload_cancels_it(tmp_path):
    config = validate(
        {
            "schemaVersion": 2,
            "enabled": True,
            "dryRun": False,
            "allowGroups": [[instance_key("test", "channel"), "group"]],
            "defaults": {
                "mode": "always",
                "cooldownSeconds": 0,
                "debounceMs": 0,
                "randomDelayMinMs": 0,
                "randomDelayMaxMs": 0,
                "maxBotReplyRatio": 1,
            },
        }
    )
    runtime = Runtime(config, tmp_path / "state.db")
    policy = SimpleNamespace(enabled=True, visibility="all")
    channel = SimpleNamespace(
        plugin_group_settings={}, group_context_manager=SimpleNamespace(policy_for=lambda _: policy)
    )
    started, release, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cancelled = []

    def inbound(ident):
        return models.InboundMessage(
            channel_id="channel",
            channel_type="test",
            tenant_id="agent",
            content=[models.TextContent(text="question")],
            metadata={
                "chat_type": "group",
                "conversation_id": "group",
                "sender_id": "user",
                "sender_is_bot": False,
                "bot_mentioned": False,
                "message_id": ident,
            },
        )

    async def dispatch(message, *, receipt, **_):
        ident = message.metadata["message_id"]
        (started if ident == "first" else second_started).set()
        try:
            if ident == "first":
                await release.wait()
                receipt.delivered = True
            else:
                await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(ident)
            raise

    try:
        await runtime.handle(channel, inbound("first"), dispatch)
        await asyncio.wait_for(started.wait(), 1)
        await runtime.handle(channel, inbound("second"), dispatch)
        await asyncio.sleep(0)
        assert cancelled == []
        assert not second_started.is_set()
        release.set()
        await asyncio.wait_for(second_started.wait(), 1)
    finally:
        await runtime.wait_closed()
    assert cancelled == ["second"]
    assert not runtime._dispatches
    gc.collect()
    assert not runtime._locks
