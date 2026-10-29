"""Optional contract test against the actual locally installed Gateway."""

import tempfile
import unittest
from unittest.mock import AsyncMock
from pathlib import Path

try:
    from octop_gateway.channels.qq.channel import QQChannel, QQConfig
    from octop_gateway.group_context import GroupContextConfig
except ImportError:
    QQChannel = None

from social_trigger.config import validate
from social_trigger.core import Engine
from social_trigger.octop import normalize


@unittest.skipIf(QQChannel is None, "octop-gateway not installed")
class QQAdapterTest(unittest.TestCase):
    def test_gateway_parse_and_core(self):
        async def processor(*args):
            if False:
                yield None

        channel = QQChannel(
            processor=processor,
            config=QQConfig(
                app_id="app",
                secret="secret",
                channel_id="instance",
                group_context=GroupContextConfig(enabled=True, visibility="all", activation="mention"),
            ),
        )
        payload = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {"id": "m1", "group_openid": "g1", "author": {"member_openid": "u1"}, "content": "question?"},
        }
        inbound = channel.parse_inbound(payload)
        normalized = normalize(inbound, agent_id="a1", visibility_granted="all", sender_is_bot=False)
        # Independent policy cannot alter the unpatched host's activation gate.
        self.assertIsNone(channel.group_context_manager.prepare(inbound))
        self.assertEqual(
            (normalized.groupId, normalized.messageId, normalized.senderId, normalized.isMentioned),
            ("g1", "m1", "u1", False),
        )
        cfg = validate(
            {
                "enabled": True,
                "dryRun": False,
                "defaults": {"mode": "always", "randomDelayMinMs": 0, "randomDelayMaxMs": 0},
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Engine(cfg, Path(directory) / "state.db").evaluate(normalized).action, "trigger")
        payload["t"] = "GROUP_AT_MESSAGE_CREATE"
        mentioned = normalize(
            channel.parse_inbound(payload), agent_id="a1", visibility_granted="limited", sender_is_bot=False
        )
        self.assertTrue(mentioned.isMentioned)


@unittest.skipIf(QQChannel is None, "octop-gateway not installed")
class QQDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_always_processes_non_mention_after_dispatch(self):
        from octop_gateway.models import MessageEvent

        calls = []

        async def processor(inbound):
            calls.append(inbound)
            yield MessageEvent.completed()

        policy = GroupContextConfig(enabled=True, visibility="all", activation="always", owner_tools_only=True)
        channel = QQChannel(processor=processor, config=QQConfig(app_id="app", secret="secret", group_context=policy))
        channel._send_text = AsyncMock()
        enqueued = []
        channel.set_enqueue_callback(enqueued.append)
        event = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {
                "id": "full1",
                "group_openid": "g",
                "author": {"member_openid": "u"},
                "content": "ordinary test message",
            },
        }
        with self.assertLogs("octop_gateway.channels.qq.channel", level="INFO"):
            await channel._handle_dispatch(event["t"], event["d"], event)
        self.assertEqual(len(enqueued), 1)
        await channel.handle_inbound(enqueued[0])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].allowed_tools, [])

    async def test_non_mention_event_is_enqueued_before_activation(self):
        async def processor(*args):
            if False:
                yield None

        channel = QQChannel(processor=processor, config=QQConfig(app_id="app", secret="secret"))
        received = []
        channel.set_enqueue_callback(received.append)
        event = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {"id": "m", "group_openid": "g", "author": {"member_openid": "u"}, "content": "hello"},
        }
        with self.assertLogs("octop_gateway.channels.qq.channel", level="INFO"):
            await channel._handle_dispatch(event["t"], event["d"], event)
        self.assertEqual(received, [event])


if __name__ == "__main__":
    unittest.main()
