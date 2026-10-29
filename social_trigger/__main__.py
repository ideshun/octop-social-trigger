"""Local config inspection, offline simulation and reservation recovery."""

import argparse
import dataclasses
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

from .config import effective, load
from .core import Engine, Message


def main():
    parser = argparse.ArgumentParser(description="Local Social Trigger administration; never sends messages")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "simulate", "status", "resolve"):
        p = sub.add_parser(command)
        p.add_argument("config")
        if command == "simulate":
            p.add_argument("message", help="normalized Message JSON")
        elif command == "check":
            p.add_argument("--scope", nargs=4, metavar=("PLATFORM", "INSTANCE", "GROUP", "AGENT"))
        else:
            p.add_argument("database")
            if command == "resolve":
                p.add_argument("reservation")
                p.add_argument(
                    "--outcome",
                    choices=("sent", "not_sent"),
                    required=True,
                    help="Use only after confirming the actual platform outcome",
                )
    args = parser.parse_args()
    try:
        config = load(args.config)
        if args.command == "check":
            out = {
                "valid": True,
                "enabled": config["enabled"],
                "dryRun": config["dryRun"],
                "hostContract": "inbound-v1",
            }
            if args.scope:
                out["effective"], out["sources"] = effective(config, *args.scope)
        elif args.command == "simulate":
            message = Message(**json.loads(Path(args.message).read_text(encoding="utf-8")))
            with tempfile.TemporaryDirectory() as temp:
                out = dataclasses.asdict(Engine(config, Path(temp) / "simulation.db").evaluate(message))
            out["simulation"] = True
        else:
            database = Path(args.database).resolve(strict=True)
            if args.command == "status":
                with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                    totals = dict(db.execute("SELECT status,COUNT(*) FROM replies GROUP BY status"))
                    pending = [
                        {
                            "reservationId": ident,
                            "scopeHash": hashlib.sha256(scope.encode()).hexdigest()[:16],
                            "reservedAt": at,
                        }
                        for ident, scope, at in db.execute("SELECT id,scope,at FROM replies WHERE status='pending'")
                    ]
                out = {
                    "enabled": config["enabled"],
                    "dryRun": config["dryRun"],
                    "replyRecords": totals,
                    "pending": pending,
                }
            else:
                if not re.fullmatch(r"[0-9a-f]{32}", args.reservation):
                    raise ValueError("reservation must be a 32-character hexadecimal ID")
                out = {"resolved": Engine(config, database).finalize(args.reservation, sent=args.outcome == "sent")}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except (ValueError, TypeError, OSError, KeyError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
