import concurrent.futures
import random
import multiprocessing
import tempfile
import unittest
from pathlib import Path

from social_trigger.config import effective, validate
from social_trigger.core import Engine, Message

NOW = 1793203200.0


def config(**overrides):
    defaults = {"mode": "always", "cooldownSeconds": 0, "randomDelayMinMs": 0, "randomDelayMaxMs": 0}
    defaults.update(overrides)
    return validate({"enabled": True, "dryRun": False, "defaults": defaults})


def message(**overrides):
    values = dict(
        platform="qq",
        channelInstanceId="c",
        groupId="g",
        agentId="a",
        messageId="1",
        senderId="u",
        text="hello?",
        receivedAt=NOW,
        visibilityGranted="all",
    )
    values.update(overrides)
    return Message(**values)


def process_attempt(args):
    path, index = args
    return (
        Engine(config(maxPassiveRepliesPerHour=1), path, clock=lambda: NOW)
        .evaluate(message(messageId=str(index)))
        .action
    )


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.db"
        self.engine = Engine(config(), self.path, clock=lambda: NOW, rng=random.Random(1))

    def test_safe_routing_and_visibility(self):
        self.assertEqual(self.engine.evaluate(message(isMentioned=True)).action, "pass")
        self.assertEqual(self.engine.evaluate(message(isCommand=True)).action, "pass")
        self.assertEqual(self.engine.evaluate(message(isGroup=False)).action, "pass")
        self.assertEqual(self.engine.evaluate(message(visibilityGranted="unknown")).reasonCode, "permission_downgraded")
        self.assertEqual(self.engine.evaluate(message(isBotMessage=True)).reasonCode, "bot_message")
        self.assertEqual(self.engine.evaluate(message(text=" ")).reasonCode, "empty_text")
        disabled = Engine(config(mode="disabled"), self.path, clock=lambda: NOW)
        self.assertEqual(disabled.evaluate(message(visibilityGranted="unknown", isBotMessage=True)).action, "pass")

    def test_modes_and_dry_run(self):
        for mode, probability, expected in [
            ("mention_only", 1, "mention_only"),
            ("probability", 0, "probability"),
            ("smart", 1, "score_below_threshold"),
        ]:
            engine = Engine(config(mode=mode, replyProbability=probability), self.path, clock=lambda: NOW)
            self.assertEqual(engine.evaluate(message(messageId=mode)).reasonCode, expected)
        cfg = config(mode="probability", replyProbability=1)
        cfg["dryRun"] = True
        dry = Engine(cfg, self.path, clock=lambda: NOW)
        self.assertEqual(dry.evaluate(message(messageId="dry")).reasonCode, "dry_run_would_trigger")
        self.assertEqual(dry.evaluate(message(messageId="dry")).action, "skip")
        self.assertIsNone(dry.evaluate(message(messageId="dry")).reservationId)

    def test_dedupe_isolation_and_finalize(self):
        d = self.engine.evaluate(message())
        self.assertEqual(d.action, "trigger")
        self.assertEqual(self.engine.evaluate(message()).reasonCode, "duplicate")
        self.assertEqual(self.engine.evaluate(message(groupId="other")).action, "trigger")
        self.assertEqual(self.engine.evaluate(message(agentId="other")).action, "trigger")
        self.assertEqual(self.engine.evaluate(message(tenantId="other")).action, "trigger")
        self.assertTrue(self.engine.finalize(d.reservationId, sent=False))
        self.assertFalse(self.engine.finalize(d.reservationId, sent=True))

    def test_atomic_quota_across_workers_and_restart(self):
        cfg = config(maxPassiveRepliesPerHour=1)

        def attempt(n):
            return Engine(cfg, self.path, clock=lambda: NOW).evaluate(message(messageId=str(n)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            decisions = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(d.action == "trigger" for d in decisions), 1)
        pending = next(d for d in decisions if d.reservationId)
        self.assertTrue(self.engine.finalize(pending.reservationId, sent=True))
        self.assertEqual(attempt(50).reasonCode, "hourly_limit")

    def test_quota_shared_by_processes(self):
        # Initialize the database before starting independent processes.
        Engine(config(maxPassiveRepliesPerHour=1), self.path, clock=lambda: NOW)
        ctx = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(max_workers=3, mp_context=ctx) as pool:
            actions = list(pool.map(process_attempt, [(self.path, i) for i in range(9)]))
        self.assertEqual(actions.count("trigger"), 1)

    def test_pending_turn_blocks_later_turns_across_restart(self):
        first = self.engine.evaluate(message(messageId="first"))
        restarted = Engine(config(), self.path, clock=lambda: NOW + 100000)
        self.assertEqual(restarted.evaluate(message(messageId="later")).reasonCode, "reply_pending")
        self.assertTrue(restarted.finalize(first.reservationId, sent=False))
        self.assertEqual(restarted.evaluate(message(messageId="after-release")).action, "trigger")

    def test_day_quota_and_reservation_release(self):
        cfg = config(maxPassiveRepliesPerDay=1)
        engine = Engine(cfg, self.path, clock=lambda: NOW)
        pending = engine.evaluate(message(messageId="pending"))
        self.assertEqual(engine.evaluate(message(messageId="blocked")).reasonCode, "daily_limit")
        self.assertTrue(engine.finalize(pending.reservationId, sent=False))
        self.assertEqual(engine.evaluate(message(messageId="released")).action, "trigger")

    def test_quiet_hours_and_cooldown(self):
        # 2026-10-29 00:00 in Shanghai.
        t = 1793203200.0
        engine = Engine(
            config(quietHours={"enabled": True, "start": "23:00", "end": "08:00"}), self.path, clock=lambda: t
        )
        self.assertEqual(engine.evaluate(message()).reasonCode, "quiet_hours")
        engine = Engine(config(cooldownSeconds=180), self.path, clock=lambda: t)
        self.assertEqual(engine.evaluate(message(messageId="first")).action, "trigger")
        self.assertEqual(engine.evaluate(message(messageId="second")).reasonCode, "cooldown")

    def test_config_overrides_and_validation(self):
        cfg = validate(
            {
                "channelTypes": {"qq": {"mode": "always"}},
                "groups": {"c": {"g": {"mode": "mention_only"}}},
                "groupAgents": {"c": {"g": {"a": {"replyProbability": 0}}}},
            }
        )
        p, sources = effective(cfg, "qq", "c", "g", "a")
        self.assertEqual((p["mode"], p["replyProbability"], sources["mode"]), ("mention_only", 0, "groups"))
        self.assertTrue(validate({"defaults": {"classifier": {"enabled": False}}})["defaults"]["decisionModelEnabled"])
        for invalid in (
            {"defaults": {"mode": "ALWAYS"}},
            {"enabled": 1},
            {"defaults": {"replyProbability": 1.1}},
            {"defaults": {"decisionModelEnabled": 1}},
            {"defaults": {"classifier": {"enabled": True}}},
        ):
            with self.assertRaises(ValueError):
                validate(invalid)

    def test_smart_reply_and_delay(self):
        engine = Engine(
            config(mode="smart", replyProbability=1, randomDelayMinMs=10, randomDelayMaxMs=10),
            self.path,
            clock=lambda: NOW,
        )
        d = engine.evaluate(message(isReplyToBot=True))
        self.assertEqual((d.action, d.delayMs, d.evaluatedScore), ("delay", 10, 1.0))

    def test_decision_score_preflight_and_fallback_preserve_limits(self):
        cfg = config(mode="smart", replyProbability=1, maxBotReplyRatio=1)
        engine = Engine(cfg, self.path, clock=lambda: NOW)
        msg = message(messageId="model", text="ordinary message")
        self.assertEqual(engine.evaluate(msg, preflight=True).action, "classify")
        decision = engine.evaluate(msg, model_score=0.9)
        self.assertEqual((decision.action, decision.evaluatedScore), ("trigger", 0.9))
        self.assertEqual(engine.evaluate(msg).reasonCode, "duplicate")
        self.assertTrue(engine.finalize(decision.reservationId, sent=False))
        blocked = Engine(config(mode="smart", maxPassiveRepliesPerHour=0), self.path, clock=lambda: NOW)
        self.assertEqual(blocked.evaluate(message(messageId="blocked"), preflight=True).reasonCode, "hourly_limit")
        fallback = Engine(cfg, self.path, clock=lambda: NOW)
        self.assertEqual(fallback.evaluate(message(messageId="fallback"), model_score=float("nan")).reasonCode, "score_below_threshold")
        self.assertEqual(fallback.evaluate(message(messageId="model-low", isReplyToBot=True), model_score=0.1).reasonCode, "score_below_threshold")
        probability = Engine(config(mode="smart", replyProbability=0, maxBotReplyRatio=1), self.path, clock=lambda: NOW)
        self.assertEqual(probability.evaluate(message(messageId="probability"), model_score=0.9).reasonCode, "probability")

    def test_decision_call_budget_is_atomic(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.engine.reserve_classifier_call(3), range(12)))
        self.assertEqual(sum(results), 3)

    def test_consecutive_replies_reset_after_fresh_human_input(self):
        engine = Engine(config(maxConsecutiveReplies=1, maxBotReplyRatio=1), self.path, clock=lambda: NOW)
        first = engine.evaluate(message(messageId="first"))
        engine.finalize(first.reservationId, sent=True)
        self.assertEqual(engine.evaluate(message(messageId="old-input")).reasonCode, "consecutive_limit")
        self.assertEqual(engine.evaluate(message(messageId="fresh-input", receivedAt=NOW + 1)).action, "trigger")

    def test_bot_ratio_and_mention_cooldown(self):
        engine = Engine(config(mentionBypassCooldown=False, cooldownSeconds=180), self.path, clock=lambda: NOW)
        first = engine.evaluate(message(messageId="first"))
        engine.finalize(first.reservationId, sent=True)
        self.assertEqual(engine.evaluate(message(isMentioned=True)).reasonCode, "mention_cooldown")
        other = Engine(config(), self.path, clock=lambda: NOW)
        self.assertEqual(other.evaluate(message(isMentioned=True)).action, "pass")
        self.assertEqual(other.evaluate(message(messageId="ratio")).reasonCode, "bot_reply_ratio")

    def test_smart_context_topic_and_activity(self):
        engine = Engine(config(mode="smart", replyProbability=1), self.path, clock=lambda: NOW)
        context = [
            message(messageId="a", text="python concurrency", senderId="one"),
            message(messageId="b", text="python tasks", senderId="two"),
        ]
        decision = engine.evaluate(message(messageId="new", text="python tasks?"), context=context)
        self.assertEqual(decision.action, "trigger")
        self.assertGreaterEqual(decision.evaluatedScore, 0.7)

    def test_storage_failure_is_safe(self):
        self.engine.database = str(self.path / "missing")
        self.assertEqual(self.engine.evaluate(message()).reasonCode, "evaluation_failed")
        self.assertEqual(self.engine.evaluate(message(isMentioned=True)).action, "pass")


if __name__ == "__main__":
    unittest.main()
