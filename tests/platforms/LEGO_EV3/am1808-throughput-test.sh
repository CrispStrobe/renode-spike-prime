#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

renode_dll=${1:-output/bin/Release/Renode.dll}
result=${2:-/tmp/ev3-arm9-throughput.json}
elf=${3:-tests/platforms/LEGO_EV3/am1808-smoke.elf}
passes=${EV3_THROUGHPUT_PASSES:-5}
interval=${EV3_THROUGHPUT_INTERVAL:-1.0}
guest_rate=300000000

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
counts=$work/counts.txt
uart=$work/uart.log
log=$work/renode.log

record_count() {
    local mode=$1
    printf 'python "f=open(\x27%s\x27,\x27%s\x27); f.write(str(self.Machine[\x27sysbus.cpu\x27].ExecutedInstructions)+\x27\\n\x27); f.close()"' "$counts" "$mode"
}

commands="mach create; machine LoadPlatformDescription @platforms/boards/lego-ev3.repl; sysbus LoadELF @$elf; uart1 CreateFileBackend @$uart true; emulation SetGlobalAdvanceImmediately true; emulation RunFor \"$interval\"; $(record_count w)"
for ((i = 0; i < passes; ++i)); do
    commands+="; emulation RunFor \"$interval\"; $(record_count a)"
done
commands+='; q'

dotnet "$renode_dll" --disable-gui --plain -e "$commands" | tee "$log"
test "$(cat "$uart")" = "EV3 ARM9 IRQ"

python3 - "$counts" "$log" "$result" "$guest_rate" "$interval" "$passes" <<'PY'
import datetime
import json
import pathlib
import re
import statistics
import sys

counts_path, log_path, result_path = map(pathlib.Path, sys.argv[1:4])
guest_rate = int(sys.argv[4])
interval = float(sys.argv[5])
pass_count = int(sys.argv[6])
counts = [int(value) for value in counts_path.read_text().splitlines()]
if len(counts) != pass_count + 1:
    raise SystemExit(f"expected {pass_count + 1} counters, got {counts}")

pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{4}).*Machine (started|resumed|paused)")
events = [match for line in log_path.read_text().splitlines()
          if (match := pattern.search(line))]
pairs = []
start = None
for event in events:
    if event.group(5) in ("started", "resumed"):
        start = event
    elif start is not None:
        pairs.append((start, event))
        start = None
if len(pairs) < pass_count + 1:
    raise SystemExit(f"expected at least {pass_count + 1} timing pairs, got {len(pairs)}")

def seconds(match):
    hour, minute, second, fraction = map(int, match.groups()[:4])
    return hour * 3600 + minute * 60 + second + fraction / 10000

samples = []
expected_instructions = guest_rate * interval
for index, ((started, stopped), before, after) in enumerate(
        zip(pairs[-pass_count:], counts, counts[1:]), 1):
    wall = seconds(stopped) - seconds(started)
    if wall < 0:
        wall += 86400
    instructions = after - before
    if not 0.98 * expected_instructions <= instructions <= 1.02 * expected_instructions:
        raise SystemExit(
            f"pass {index}: expected about {expected_instructions:.0f} instructions, "
            f"got {instructions}"
        )
    mips = instructions / wall / 1_000_000
    samples.append({
        "pass": index,
        "guest_instructions": instructions,
        "wall_seconds": wall,
        "throughput_mips": mips,
        "rtx_at_300_mhz": mips / 300,
    })

report = {
    "benchmark": "Renode LEGO EV3 AM1808 ARM926EJ-S unpaced throughput",
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "advance_immediately": True,
    "platform_performance_mips": guest_rate / 1_000_000,
    "warmup_virtual_seconds": interval,
    "pass_virtual_seconds": interval,
    "passes": samples,
    "uart_smoke": "EV3 ARM9 IRQ\n",
    "summary": {
        "median_mips": statistics.median(sample["throughput_mips"] for sample in samples),
        "median_rtx_at_300_mhz": statistics.median(sample["rtx_at_300_mhz"] for sample in samples),
        "min_rtx_at_300_mhz": min(sample["rtx_at_300_mhz"] for sample in samples),
        "max_rtx_at_300_mhz": max(sample["rtx_at_300_mhz"] for sample in samples),
    },
    "method": (
        "One process; pacing disabled; one warm-up then fixed virtual-time passes; "
        "exact ExecutedInstructions deltas divided by start/pause wall intervals."
    ),
}
result_path.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY
