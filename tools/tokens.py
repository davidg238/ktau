#!/usr/bin/env python3
"""Sum Claude Code token usage between two UTC times, for a rung's journal entry.

    tools/tokens.py START [END] [transcript.jsonl ...]

START and END are ISO times (2026-11-19T20:55:04Z); END defaults to now. With no transcripts given,
every .jsonl under ~/.claude/projects/ is read, subagent transcripts included. Each assistant message
is counted once, by message id, because a streamed message is written on several lines.
"""
import datetime, glob, json, os, sys


def when(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def main(argv):
    start = when(argv[1])
    rest = argv[2:]
    end = datetime.datetime.now(datetime.timezone.utc)
    if rest and not rest[0].endswith(".jsonl"):
        end = when(rest.pop(0))
    paths = rest or glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True)
    seen = {}
    for path in paths:
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict) or "usage" not in msg or "timestamp" not in rec:
                    continue
                if not start <= when(rec["timestamp"]) < end:
                    continue
                seen[msg.get("id") or (path, rec.get("uuid"))] = msg["usage"]
    keys = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"]
    total = {k: sum(u.get(k) or 0 for u in seen.values()) for k in keys}
    print(f"messages {len(seen)}")
    for k in keys:
        print(f"{k} {total[k]}")


if __name__ == "__main__":
    main(sys.argv)
