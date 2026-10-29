"""Platform-independent decisions; host integration must occur before agent dispatch."""

from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import effective


@dataclass(frozen=True)
class Message:
    platform: str
    channelInstanceId: str
    groupId: str
    agentId: str
    messageId: str
    senderId: str
    text: str
    receivedAt: float
    isMentioned: bool = False
    isReplyToBot: bool = False
    isBotMessage: bool = False
    isCommand: bool = False
    isGroup: bool = True
    visibilityGranted: str = "unknown"
    tenantId: str = ""

    def __post_init__(self):
        for name in ("platform", "channelInstanceId", "groupId", "agentId", "senderId"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name}: expected nonempty stable ID")
        if not isinstance(self.messageId, str) or not isinstance(self.tenantId, str) or not isinstance(self.text, str):
            raise ValueError("messageId, tenantId and text must be strings")
        if type(self.receivedAt) not in (float, int) or not 0 < self.receivedAt < 253402300800:
            raise ValueError("receivedAt: expected Unix timestamp")
        for name in ("isMentioned", "isReplyToBot", "isBotMessage", "isCommand", "isGroup"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name}: expected boolean")
        if self.visibilityGranted not in ("all", "limited", "unknown"):
            raise ValueError("visibilityGranted: invalid visibility")


@dataclass(frozen=True)
class Decision:
    action: str
    reasonCode: str
    dedupeKey: str = ""
    delayMs: int = 0
    evaluatedScore: float | None = None
    reservationId: str | None = None
    dryRun: bool = False


class Engine:
    """SQLite serializes decisions across processes sharing one database.

    Pending reservations never expire automatically: the host must explicitly
    commit or release them to avoid exceeding quotas after crashes.
    """

    def __init__(self, config, database, *, rng=None, clock=time.time):
        self.config, self.database = config, str(database)
        self.rng, self.clock = rng or random.Random(), clock
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS seen (scope TEXT NOT NULL, id TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS replies (id TEXT PRIMARY KEY, scope TEXT NOT NULL, at REAL NOT NULL, status TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS replies_scope ON replies(scope,at);
                CREATE TABLE IF NOT EXISTS streak (scope TEXT PRIMARY KEY, count INTEGER NOT NULL, last_sent REAL NOT NULL);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            yield db
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _identity(m):
        scope = json.dumps(
            [m.tenantId, m.channelInstanceId, m.groupId, m.agentId], ensure_ascii=False, separators=(",", ":")
        )
        native_id = (
            m.messageId or hashlib.sha256(f"{m.senderId}\0{m.text}\0{int(m.receivedAt // 10)}".encode()).hexdigest()
        )
        return scope, native_id

    def accept_ingress(self, message):
        scope, native_id = self._identity(message)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM seen WHERE at < ?", (self.clock() - 86400,))
            inserted = db.execute(
                "INSERT OR IGNORE INTO seen VALUES (?,?,?)", (scope, "ingress:" + native_id, self.clock())
            ).rowcount
            db.commit()
            return inserted == 1

    def evaluate(self, m: Message, *, context=()) -> Decision:
        # The host remains responsible for its normal routing of mentions,
        # commands, and direct messages. Never block those paths here.
        if not m.isGroup or m.isCommand or m.text.lstrip().startswith("/"):
            return Decision("pass", "host_route")
        if not self.config["enabled"]:
            return Decision("pass", "plugin_disabled")
        try:
            policy, _ = effective(self.config, m.platform, m.channelInstanceId, m.groupId, m.agentId)
            if policy["mode"] == "disabled":
                return Decision("pass", "policy_disabled")
            if m.isBotMessage:
                return Decision("skip", "bot_message")
            if m.isMentioned:
                if not policy["mentionBypassCooldown"]:
                    with self._connect() as db:
                        row = db.execute(
                            "SELECT MAX(at) FROM replies WHERE scope=?", (self._identity(m)[0],)
                        ).fetchone()
                    if row and row[0] is not None and self.clock() - row[0] < policy["cooldownSeconds"]:
                        return Decision("skip", "mention_cooldown")
                return Decision("pass", "host_route")
            if not m.text.strip():
                return Decision("skip", "empty_text")
            group = [m.channelInstanceId, m.groupId]
            if group in self.config["denyGroups"] or (
                self.config["allowGroups"] and group not in self.config["allowGroups"]
            ):
                return Decision("skip", "group_not_allowed")
            if m.visibilityGranted != "all":
                return Decision("skip", "permission_downgraded")
            return self._evaluate(m, policy, context)
        except (sqlite3.Error, ValueError, OverflowError):
            return Decision("pass" if m.isMentioned else "skip", "evaluation_failed")

    def _evaluate(self, m, p, context):
        now = self.clock()
        scope, native_id = self._identity(m)
        fallback = not m.messageId
        dedupe = hashlib.sha256((scope + "\0" + native_id).encode()).hexdigest()
        dry = self.config["dryRun"]

        def result(action, reason, **kw):
            return Decision(action, reason, dedupeKey=dedupe, dryRun=dry, **kw)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM seen WHERE at < ?", (now - 86400,))
            db.execute("DELETE FROM replies WHERE status='sent' AND at < ?", (now - 259200,))
            if db.execute("SELECT 1 FROM seen WHERE scope=? AND id=?", (scope, native_id)).fetchone():
                db.commit()
                return result("skip", "duplicate")
            if not dry:
                db.execute("INSERT INTO seen VALUES (?,?,?)", (scope, native_id, now))
            if p["mode"] == "mention_only":
                db.commit()
                return result("skip", "mention_only")
            local = datetime.fromtimestamp(now, ZoneInfo(self.config["timezone"]))
            quiet = p["quietHours"]
            minute = local.hour * 60 + local.minute
            start, end = (int(x[:2]) * 60 + int(x[3:]) for x in (quiet["start"], quiet["end"]))
            if quiet["enabled"] and (
                start == end or (start <= minute < end if start < end else minute >= start or minute < end)
            ):
                db.commit()
                return result("skip", "quiet_hours")
            rows = db.execute(
                "SELECT at, status FROM replies WHERE scope=? AND status IN ('pending','sent')", (scope,)
            ).fetchall()
            times = [row[0] for row in rows]
            if times and now - max(times) < p["cooldownSeconds"]:
                db.commit()
                return result("skip", "cooldown")
            if sum(status == "pending" or t > now - 3600 for t, status in rows) >= p["maxPassiveRepliesPerHour"]:
                db.commit()
                return result("skip", "hourly_limit")
            if (
                sum(
                    status == "pending"
                    or datetime.fromtimestamp(t, ZoneInfo(self.config["timezone"])).date() == local.date()
                    for t, status in rows
                )
                >= p["maxPassiveRepliesPerDay"]
            ):
                db.commit()
                return result("skip", "daily_limit")
            # ponytail: one pending reply per scope; use a host-backed send
            # coordinator if concurrent passive turns are ever required.
            if any(status == "pending" for _, status in rows):
                db.commit()
                return result("skip", "reply_pending")
            humans = db.execute(
                "SELECT COUNT(*) FROM seen WHERE scope=? AND id LIKE 'ingress:%' AND at>?",
                (scope, now - p["contextTtlSeconds"]),
            ).fetchone()[0]
            bot_replies = sum(t > now - p["contextTtlSeconds"] for t in times)
            # Direct engine simulations have no ingress stream; count their explicit context.
            humans = max(humans, len(context) + 1)
            if bot_replies / (humans + bot_replies) >= p["maxBotReplyRatio"]:
                db.commit()
                return result("skip", "bot_reply_ratio")
            prior = db.execute("SELECT count,last_sent FROM streak WHERE scope=?", (scope,)).fetchone()
            if prior and m.receivedAt > prior[1]:
                db.execute("UPDATE streak SET count=0 WHERE scope=?", (scope,))
            elif prior and prior[0] >= p["maxConsecutiveReplies"]:
                db.commit()
                return result("skip", "consecutive_limit")
            if p["mode"] == "smart":
                # Conservative, explainable signals; no classifier or persona assumptions.
                terms = set(re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2}", m.text.lower()))
                recent = [
                    item
                    for item in context
                    if self._identity(item)[0] == scope
                    and item.visibilityGranted == "all"
                    and not item.isBotMessage
                    and 0 <= now - item.receivedAt < p["contextTtlSeconds"]
                ]
                overlap = any(
                    terms.intersection(re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2}", item.text.lower()))
                    for item in recent
                )
                hot = len(recent) >= 2 and len({item.senderId for item in [*recent, m]}) >= 2
                score = min(
                    1.0,
                    (0.7 if m.isReplyToBot else 0)
                    + (0.3 if re.search(r"[?？]", m.text) else 0)
                    + (0.35 if overlap else 0)
                    + (0.15 if hot else 0),
                )
                if score < p["smartScoreThreshold"]:
                    db.commit()
                    return result("skip", "score_below_threshold", evaluatedScore=score)
            else:
                score = None
            if p["mode"] in ("smart", "probability") and self.rng.random() >= p["replyProbability"]:
                db.commit()
                return result("skip", "probability", evaluatedScore=score)
            delay = self.rng.randint(p["randomDelayMinMs"], p["randomDelayMaxMs"])
            reservation = None
            if not dry:
                reservation = uuid.uuid4().hex
                db.execute("INSERT INTO replies VALUES (?,?,?, 'pending')", (reservation, scope, now))
            db.commit()
            if dry:
                return result("skip", "dry_run_would_trigger", delayMs=delay, evaluatedScore=score)
            return result(
                "delay" if delay else "trigger",
                "fallback_id" if fallback else "eligible",
                delayMs=delay,
                evaluatedScore=score,
                reservationId=reservation,
            )

    def finalize(self, reservation_id: str, *, sent: bool):
        """Call only after confirmed send; release on cancellation/failure."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT scope FROM replies WHERE id=? AND status='pending'", (reservation_id,)).fetchone()
            if row is None:
                db.commit()
                return False
            if sent:
                now = self.clock()
                cursor = db.execute(
                    "UPDATE replies SET status='sent', at=? WHERE id=? AND status='pending'", (now, reservation_id)
                )
                db.execute(
                    "INSERT INTO streak VALUES (?,1,?) ON CONFLICT(scope) DO UPDATE SET count=count+1,last_sent=excluded.last_sent",
                    (row[0], now),
                )
            else:
                cursor = db.execute("DELETE FROM replies WHERE id=? AND status='pending'", (reservation_id,))
            db.commit()
            return cursor.rowcount == 1
