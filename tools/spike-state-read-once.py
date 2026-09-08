#!/usr/bin/env python3
"""Read and validate one snapshot from the loopback SPIKE state service."""

import argparse
import json
import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from spike_state_bridge import parse_line


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("--board", required=True)
    parser.add_argument("--firmware", required=True)
    arguments = parser.parse_args()
    with socket.create_connection((arguments.host, arguments.port), timeout=5) as connection:
        stream = connection.makefile("rb")
        snapshot = parse_line(stream.readline())
    if snapshot.get("type") != "snapshot":
        raise ValueError("state service did not return a snapshot")
    target = snapshot["target"]
    if target["board"] != arguments.board or target["firmware"] != arguments.firmware:
        raise ValueError("state service returned the wrong target identity")
    print(json.dumps(snapshot, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
