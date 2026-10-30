"""Offline end-to-end contract tests for patched Gateway and Harness."""

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

try:
    from octop_gateway.channel import InboundReceipt
    from octop_gateway.channels.qq.channel import QQChannel, QQConfig
    from octop_gateway.group_context import GroupContextConfig
    from octop_gateway.manager import ChannelManager
    from octop_gateway.models import MessageEvent
    from octop_harness.plugins.context import PluginContext

    SUPPORTED = callable(InboundReceipt) and hasattr(PluginContext, "inbound")
except ImportError:
    SUPPORTED = False

from social_trigger.config import load, validate
from social_trigger.runtime import Runtime


async def wait_for(predicate, timeout=1):
    until = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= until:
            raise AssertionError("condition timed out")
        await asyncio.sleep(0.005)


@unittest.skipUnless(SUPPORTED, "requires inbound-v1 compatibility patches")
class Integration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []

        async def process(message):
            self.calls.append(message)
            yield MessageEvent.text("test reply")
            yield MessageEvent.completed()

        self.channel = QQChannel(
            processor=process,
            tenant_id="agent",
            config=QQConfig(
                app_id="offline",
                secret="offline",
                channel_id="instance",
                tenant_id="agent",
                group_context=GroupContextConfig(
                    enabled=True, visibility="all", activation="mention", owner_tools_only=True
                ),
            ),
        )
        self.channel.start = AsyncMock()
        self.channel.stop = AsyncMock()
        self.channel._send_text = AsyncMock()
        self.managers = []
        self.runtimes = []

    async def runtime(self, **settings):
        defaults = dict(mode="always", cooldownSeconds=0, debounceMs=20, randomDelayMinMs=0, randomDelayMaxMs=0)
        defaults.update(settings.pop("defaults", {}))
        cfg = dict(enabled=True, dryRun=False, defaults=defaults)
        cfg.update(settings)
        runtime = Runtime(validate(cfg), Path(self.temp.name) / (str(len(self.runtimes)) + ".db"))
        manager = ChannelManager(
            {self.channel.channel_id: self.channel}, workers_per_channel=4, inbound_handler=runtime.handle
        )
        self.runtimes.append(runtime)
        self.managers.append(manager)
        await manager.start()
        return runtime, manager

    async def asyncTearDown(self):
        for runtime in self.runtimes:
            await runtime.wait_closed()
        for manager in self.managers:
            await manager.stop()

    def event(self, ident, *, mentioned=False, bot=False, group="group", content=None):
        return {
            "t": "GROUP_AT_MESSAGE_CREATE" if mentioned else "GROUP_MESSAGE_CREATE",
            "d": {
                "id": ident,
                "group_openid": group,
                "timestamp": time.time(),
                "author": {"member_openid": "human", "bot": bot},
                "content": content or ident,
            },
        }

    def send(self, manager, ident, **kw):
        manager.enqueue(self.channel.channel_id, self.event(ident, **kw))

    async def test_five_messages_merge_before_agent_and_commit_once(self):
        runtime, manager = await self.runtime()
        for n in range(5):
            self.send(manager, str(n))
        await wait_for(lambda: len(self.calls) == 1 and not runtime._tasks)
        self.assertEqual(self.calls[0].text, "4")
        self.assertEqual(len(self.calls[0].group_context.messages), 4)
        self.assertEqual(self.calls[0].allowed_tools, [])
        with runtime.engine._connect() as db:
            self.assertEqual(db.execute("select count(*) from replies where status='sent'").fetchone()[0], 1)
        self.channel._send_text.assert_awaited_once()

    async def test_skip_and_dry_run_use_no_agent(self):
        runtime, manager = await self.runtime(defaults={"mode": "probability", "replyProbability": 0})
        self.send(manager, "zero")
        await wait_for(lambda: bool(runtime.recent) and not runtime._tasks)
        self.assertEqual(self.calls, [])
        runtime.config["dryRun"] = True
        runtime.config["defaults"]["replyProbability"] = 1
        self.send(manager, "dry")
        await wait_for(lambda: any(r["reasonCode"] == "dry_run_would_trigger" for r in runtime.recent))
        self.assertEqual(self.calls, [])

    async def test_decision_model_scores_smart_mode_without_calling_agent_in_dry_run(self):
        scorer = AsyncMock(return_value={"participate": 0.95})
        provider = AsyncMock(return_value=scorer)
        runtime, manager = await self.runtime(dryRun=True, defaults={"mode": "smart", "replyProbability": 1})
        runtime.bind_decision_scorer(provider)
        self.send(manager, "model-eligible", content="普通聊天")
        await wait_for(lambda: any(r["reasonCode"] == "dry_run_would_trigger" for r in runtime.recent))
        scorer.assert_awaited_once()
        state = json.loads(scorer.await_args.kwargs["state"])
        self.assertEqual(state["当前消息"], "普通聊天")
        self.assertEqual(runtime.recent[-1]["decisionSource"], "model")
        self.assertNotIn("human", scorer.await_args.kwargs["state"])
        self.assertNotIn("group", scorer.await_args.kwargs["state"])
        self.assertEqual(self.calls, [])

    async def test_decision_model_can_trigger_normal_reply(self):
        scorer = AsyncMock(return_value={"participate": 0.95})
        runtime, manager = await self.runtime(defaults={"mode": "smart", "replyProbability": 1})
        runtime.bind_decision_scorer(AsyncMock(return_value=scorer))
        self.send(manager, "model-live", content="普通聊天")
        await wait_for(lambda: len(self.calls) == 1 and not runtime._tasks)
        scorer.assert_awaited_once()
        self.channel._send_text.assert_awaited_once()
        self.assertTrue(any(r["reasonCode"] == "reply_sent" for r in runtime.recent))

    async def test_decision_model_disabled_or_failing_falls_back_to_rules(self):
        provider = AsyncMock(return_value=None)
        runtime, manager = await self.runtime(dryRun=True, defaults={"mode": "smart", "replyProbability": 1})
        runtime.bind_decision_scorer(provider)
        self.send(manager, "disabled-model", content="普通聊天")
        await wait_for(lambda: any(r["reasonCode"] == "score_below_threshold" for r in runtime.recent))
        self.assertEqual(runtime.recent[-1]["decisionSource"], "rules")
        provider.assert_awaited_once()
        scorer = AsyncMock(side_effect=RuntimeError("unavailable"))
        provider.return_value = scorer
        self.send(manager, "failed-model", content="完全不同的话")
        await wait_for(lambda: any(r["reasonCode"] == "decision_model_unavailable" for r in runtime.recent))
        await wait_for(lambda: sum(r["reasonCode"] == "score_below_threshold" for r in runtime.recent) >= 2)
        self.assertEqual(self.calls, [])

    async def test_decision_model_timeout_falls_back_and_mention_stays_native(self):
        async def slow(**_kwargs):
            await asyncio.sleep(1)
        runtime, manager = await self.runtime(
            dryRun=True,
            defaults={"mode": "smart", "replyProbability": 1, "decisionModelTimeoutMs": 30},
        )
        runtime.bind_decision_scorer(AsyncMock(return_value=slow))
        self.send(manager, "timeout-model", content="普通聊天")
        await wait_for(lambda: any(r["reasonCode"] == "score_below_threshold" for r in runtime.recent))
        self.send(manager, "mention-after-timeout", mentioned=True)
        await wait_for(lambda: len(self.calls) == 1)

    async def test_invalid_decision_response_uses_rules_and_pauses_retries(self):
        scorer = AsyncMock(return_value={"participate": float("nan")})
        provider = AsyncMock(return_value=scorer)
        runtime, manager = await self.runtime(dryRun=True, defaults={"mode": "smart", "replyProbability": 1})
        runtime.bind_decision_scorer(provider)
        self.send(manager, "invalid-model-1", content="甲乙丙丁")
        await wait_for(lambda: any(r["reasonCode"] == "decision_model_unavailable" for r in runtime.recent))
        self.send(manager, "invalid-model-2", content="天地玄黄")
        await wait_for(lambda: sum(r["reasonCode"] == "score_below_threshold" for r in runtime.recent) >= 2)
        scorer.assert_awaited_once()
        self.assertEqual(self.calls, [])

    async def test_decision_model_is_not_called_when_disabled_or_over_quota(self):
        provider = AsyncMock()
        runtime, manager = await self.runtime(
            dryRun=True, defaults={"mode": "smart", "decisionModelEnabled": False}
        )
        runtime.bind_decision_scorer(provider)
        self.send(manager, "decision-disabled", content="普通聊天")
        await wait_for(lambda: any(r["reasonCode"] == "score_below_threshold" for r in runtime.recent))
        provider.assert_not_awaited()
        runtime.config["defaults"]["decisionModelEnabled"] = True
        runtime.config["defaults"]["maxPassiveRepliesPerHour"] = 0
        self.send(manager, "over-quota", content="另一条消息")
        await wait_for(lambda: any(r["reasonCode"] == "hourly_limit" for r in runtime.recent))
        provider.assert_not_awaited()

    async def test_mention_cancels_delayed_passive_reply(self):
        runtime, manager = await self.runtime(
            defaults={"debounceMs": 0, "randomDelayMinMs": 150, "randomDelayMaxMs": 150}
        )
        self.send(manager, "pending")
        await wait_for(lambda: any(r["reasonCode"] == "eligible" for r in runtime.recent))
        self.send(manager, "mention", mentioned=True)
        await wait_for(lambda: len(self.calls) == 1)
        await asyncio.sleep(0.2)
        self.assertEqual([m.text for m in self.calls], ["mention"])
        with runtime.engine._connect() as db:
            self.assertEqual(db.execute("select count(*) from replies").fetchone()[0], 0)

    async def test_settings_save_cancels_pending_and_applies_to_group(self):
        runtime, manager = await self.runtime(
            defaults={"debounceMs": 0, "randomDelayMinMs": 300, "randomDelayMaxMs": 300},
            allowGroups=[[self.channel.channel_id, "group"]],
        )
        runtime.config_path = Path(self.temp.name) / "config.json"
        self.send(manager, "pending-settings")
        await wait_for(lambda: any(r["reasonCode"] == "eligible" for r in runtime.recent))
        await runtime.update_settings(
            enabled=True, dry_run=True, channel_id=self.channel.channel_id, group_id="group", agent_id="agent",
            policy={"mode": "probability", "replyProbability": 1, "randomDelayMinMs": 0, "randomDelayMaxMs": 0},
        )
        self.assertEqual(self.calls, [])
        self.assertTrue(load(runtime.config_path)["dryRun"])
        self.assertEqual(runtime.settings_for(self.channel.channel_id, "group", "agent")["policy"]["mode"], "probability")
        self.send(manager, "after-settings")
        await wait_for(lambda: any(r["reasonCode"] == "dry_run_would_trigger" for r in runtime.recent))
        self.assertEqual(self.calls, [])
        with runtime.engine._connect() as db:
            self.assertEqual(db.execute("select count(*) from replies").fetchone()[0], 0)

    async def test_first_settings_activation_limits_scope_to_selected_group(self):
        runtime, _ = await self.runtime(enabled=False)
        runtime.config_path = Path(self.temp.name) / "first-config.json"
        await runtime.update_settings(
            enabled=True, dry_run=True, channel_id=self.channel.channel_id, group_id="group", agent_id="agent",
            policy={"mode": "smart"},
        )
        self.assertEqual(runtime.config["allowGroups"], [[self.channel.channel_id, "group"]])

    async def test_unload_cancels_and_releases_pending(self):
        runtime, manager = await self.runtime(
            defaults={"debounceMs": 0, "randomDelayMinMs": 150, "randomDelayMaxMs": 150}
        )
        self.send(manager, "pending")
        await wait_for(lambda: any(r["reasonCode"] == "eligible" for r in runtime.recent))
        tasks = list(runtime._tasks.values())
        runtime.close()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(self.calls, [])
        with runtime.engine._connect() as db:
            self.assertEqual(db.execute("select count(*) from replies").fetchone()[0], 0)

    async def test_permission_revocation_and_missing_bot_signal(self):
        runtime, manager = await self.runtime()
        event = self.event("unknown")
        event["d"]["author"].pop("bot")
        manager.enqueue(self.channel.channel_id, event)
        await wait_for(lambda: bool(runtime.recent))
        self.assertEqual(runtime.recent[-1]["reasonCode"], "sender_identity_unknown")
        self.channel.group_context_manager._config.visibility = "mention_only"
        self.send(manager, "limited")
        await wait_for(lambda: runtime.recent[-1]["reasonCode"] == "permission_downgraded")
        self.assertEqual(self.calls, [])

    async def test_output_free_completion_releases_quota(self):
        async def process(message):
            self.calls.append(message)
            yield MessageEvent.completed()

        self.channel._processor = process
        runtime, manager = await self.runtime(defaults={"maxPassiveRepliesPerHour": 1})
        self.send(manager, "one")
        await wait_for(lambda: len(self.calls) == 1 and not runtime._tasks)
        self.send(manager, "two")
        await wait_for(lambda: len(self.calls) == 2 and not runtime._tasks)
        with runtime.engine._connect() as db:
            self.assertEqual(db.execute("select count(*) from replies").fetchone()[0], 0)

    async def test_quota_filters_and_cross_group_isolation(self):
        runtime, manager = await self.runtime(defaults={"maxPassiveRepliesPerHour": 1})
        self.send(manager, "first")
        await wait_for(lambda: len(self.calls) == 1 and not runtime._tasks)
        self.send(manager, "second")
        await wait_for(lambda: any(r["reasonCode"] == "hourly_limit" for r in runtime.recent))
        self.send(manager, "other", group="other-group")
        await wait_for(lambda: len(self.calls) == 2)
        self.assertEqual([m.metadata["conversation_id"] for m in self.calls], ["group", "other-group"])

    async def test_unselected_group_preserves_host_routing(self):
        self.channel.group_context_manager._config.activation = "always"
        runtime, manager = await self.runtime(allowGroups=[[self.channel.channel_id, "group"]])
        self.send(manager, "outside-scope", group="other-group")
        await wait_for(lambda: len(self.calls) == 1)
        self.assertEqual(self.calls[0].metadata["conversation_id"], "other-group")
        self.assertFalse(runtime.recent)

    async def test_channel_switch_disables_plugin_and_preserves_native_routing(self):
        self.channel._config.social_trigger_enabled = False
        self.channel.group_context_manager._config.activation = "always"
        runtime, manager = await self.runtime()
        self.send(manager, "channel-disabled")
        await wait_for(lambda: len(self.calls) == 1)
        self.assertEqual(runtime.recent[-1]["reasonCode"], "channel_disabled")

    @unittest.skipUnless(SUPPORTED and hasattr(QQChannel, "plugin_group_settings"), "requires plugin group settings")
    async def test_declared_channel_setting_controls_plugin(self):
        self.channel._config.plugin_group_settings = {"social_trigger_enabled": False}
        self.channel.group_context_manager._config.activation = "always"
        runtime, manager = await self.runtime()
        self.send(manager, "registered-channel-disabled")
        await wait_for(lambda: len(self.calls) == 1)
        self.assertEqual(runtime.recent[-1]["reasonCode"], "channel_disabled")

    async def test_bot_mentions_cannot_start_reply_loops(self):
        runtime, manager = await self.runtime()
        self.send(manager, "bot-at", bot=True, mentioned=True)
        await wait_for(lambda: any(r["reasonCode"] == "bot_message" for r in runtime.recent))
        self.assertEqual(self.calls, [])

    async def test_ttl_purges_idle_context_and_stops_dispatch(self):
        runtime, manager = await self.runtime(defaults={"debounceMs": 50, "contextTtlSeconds": 1})
        now = time.time()
        runtime.clock = lambda: now
        self.send(manager, "expiring")
        await wait_for(lambda: bool(runtime._buffers))
        now += 2
        for key in list(runtime._buffers):
            runtime._expire(key, 1)
        await wait_for(lambda: not runtime._tasks)
        self.assertEqual(runtime._buffers, {})
        self.assertEqual(self.calls, [])

    async def test_duplicate_platform_delivery_does_not_wake_agent_twice(self):
        runtime, manager = await self.runtime()
        self.send(manager, "same")
        await wait_for(lambda: len(self.calls) == 1 and not runtime._tasks)
        self.send(manager, "same")
        await wait_for(lambda: any(r["reasonCode"] == "duplicate" for r in runtime.recent))
        self.assertEqual(len(self.calls), 1)

    async def test_uncertain_delivery_keeps_reservation_and_prevents_retry(self):
        runtime, manager = await self.runtime()
        self.channel._send_text = AsyncMock(side_effect=TimeoutError("offline transport timeout"))
        with self.assertLogs("octop_gateway.channel", level="ERROR"):
            self.send(manager, "unknown")
            await wait_for(lambda: any(r["reasonCode"] == "delivery_unknown" for r in runtime.recent))
        self.send(manager, "next")
        await wait_for(lambda: any(r["reasonCode"] == "reply_pending" for r in runtime.recent))
        self.assertEqual(len(self.calls), 1)
        with runtime.engine._connect() as db:
            self.assertEqual(db.execute("select count(*) from replies where status='pending'").fetchone()[0], 1)

    async def test_host_rejects_forced_activation_without_all_visibility(self):
        self.channel.group_context_manager._config.visibility = "auto"
        inbound = self.channel.parse_inbound(self.event("forged"))
        receipt = await self.channel.dispatch_inbound(inbound, force_activation=True)
        self.assertFalse(receipt.attempted)
        self.assertEqual(self.calls, [])

    async def test_octop_dynamic_registry_bridge(self):
        from types import SimpleNamespace
        from octop.infra.gateway.gateway import Gateway
        from octop_harness.plugins.loader import load_plugin_dir, unload_plugin

        loaded = load_plugin_dir(Path(__file__).resolve().parents[1], install_deps=False)
        runtime, manager = await self.runtime()
        loaded.inbound = [runtime]

        async def bridge(channel, message, dispatch):
            return await Gateway._plugin_inbound(SimpleNamespace(), channel, message, dispatch)

        manager._inbound_handler = bridge
        self.send(manager, "bridged")
        await wait_for(lambda: len(self.calls) == 1 and not runtime._tasks)
        self.assertTrue(unload_plugin("octop-social-trigger"))
        self.assertTrue(runtime._closed)
        self.send(manager, "native-passive")
        await asyncio.sleep(0.03)
        self.assertEqual(len(self.calls), 1)

    async def test_octop_binds_enabled_decision_model_to_plugin(self):
        from types import SimpleNamespace
        from octop.infra.gateway.gateway import Gateway
        from octop_harness.plugins.loader import load_plugin_dir, unload_plugin

        if not hasattr(Gateway, "_decision_scorer_for_plugin"):
            self.skipTest("requires host decision-model bridge")
        from octop_harness.decision.config import DecisionConfig

        loaded = load_plugin_dir(Path(__file__).resolve().parents[1], install_deps=False)
        runtime, manager = await self.runtime(dryRun=True, defaults={"mode": "smart", "replyProbability": 1})
        loaded.inbound = [runtime]
        gateway = Gateway.__new__(Gateway)
        config = DecisionConfig(enabled=True, provider="custom", endpoint="https://example.test")
        gateway._agent_manager = SimpleNamespace(decision=SimpleNamespace(harness_config=lambda: config))
        manager._inbound_handler = gateway._plugin_inbound
        with patch("octop_harness.decision.client.HttpDecisionClient.score_async", new_callable=AsyncMock) as scorer:
            scorer.return_value = {"participate": 0.95}
            self.send(manager, "host-decision", content="普通聊天")
            await wait_for(lambda: any(r["reasonCode"] == "dry_run_would_trigger" for r in runtime.recent))
            scorer.assert_awaited_once()
            self.assertEqual(self.calls, [])
        self.assertTrue(unload_plugin("octop-social-trigger"))

    async def test_native_loader_registers_and_unloads_hook(self):
        from octop.infra.gateway import plugin_channels
        from octop_harness.plugins.loader import load_plugin_dir, unload_plugin
        from octop_harness.plugins.registry import PluginRegistry

        root = Path(__file__).resolve().parents[1]
        loaded = load_plugin_dir(root, install_deps=False)
        self.assertEqual(loaded.manifest.kind, "hook")
        self.assertEqual(len(loaded.inbound), 1)
        self.assertIs(PluginRegistry().all_inbound()[-1], loaded.inbound[0])
        get_settings = getattr(plugin_channels, "plugin_channel_settings", None)
        if get_settings:
            fields = get_settings(PluginRegistry())
            self.assertTrue(any(field["plugin_id"] == "octop-social-trigger" and field["name"] == "social_trigger_enabled" for field in fields))
        self.assertTrue(unload_plugin("octop-social-trigger"))
        if get_settings:
            self.assertFalse(any(field["plugin_id"] == "octop-social-trigger" for field in get_settings(PluginRegistry())))
        self.assertTrue(loaded.inbound[0]._closed)


if __name__ == "__main__":
    unittest.main()
