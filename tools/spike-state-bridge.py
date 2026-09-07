#!/usr/bin/env python3
"""Validate and gate neutral commands on stdin; emit canonical results."""

import argparse
import sys

from spike_state_bridge import CommandGate, ProtocolError, canonical_bytes, parse_line


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seq", type=int, default=0)
    arguments = parser.parse_args()
    if arguments.seq < 0:
        parser.error("--seq must be non-negative")
    gate = CommandGate()
    gate.seq = arguments.seq
    for line in sys.stdin.buffer:
        try:
            message = parse_line(line)
            if message["type"] != "command":
                raise ProtocolError("service input must be a command")
            result = gate.accept(message)
        except ProtocolError as error:
            result = {"schemaVersion": 1, "type": "result", "requestId": "invalid",
                      "accepted": False, "error": str(error)}
        sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
