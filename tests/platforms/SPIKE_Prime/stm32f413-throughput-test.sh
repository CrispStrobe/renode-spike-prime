#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

renode_dll=${1:-output/bin/Release/Renode.dll}
result=${2:-/tmp/spike-prime-throughput.json}
elf=${3:-tests/platforms/SPIKE_Prime/stm32f413-throughput.elf}
passes=${SPIKE_THROUGHPUT_PASSES:-5}
interval=${SPIKE_THROUGHPUT_INTERVAL:-1.0}
guest_rate=96000000
brick_state_run=https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/36416073810

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
counts=$work/counts.txt
uart=$work/uart.log
log=$work/renode.log

record_count() {
    local mode=$1
    printf 'python "f=open(\x27%s\x27,\x27%s\x27); f.write(str(self.Machine[\x27sysbus.cpu\x27].ExecutedInstructions)+\x27\\n\x27); f.close()"' "$counts" "$mode"
}

commands="mach create; machine LoadPlatformDescription @platforms/boards/spike-prime.repl; sysbus LoadELF @$elf; cpu SP 0x20050000; usart2 CreateFileBackend @$uart true; emulation SetGlobalAdvanceImmediately true; emulation RunFor \"$interval\"; $(record_count w)"
for ((i = 0; i < passes; ++i)); do
    commands+="; emulation RunFor \"$interval\"; $(record_count a)"
done
commands+='; q'

dotnet "$renode_dll" --disable-gui --plain -e "$commands" | tee "$log"
test "$(cat "$uart")" = SPIKE

python3 - "$counts" "$log" "$result" "$guest_rate" "$interval" "$passes" "$brick_state_run" <<'PY'
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
brick_state_run = sys.argv[7]
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
expected = guest_rate * interval
for index, ((started, stopped), before, after) in enumerate(
        zip(pairs[-pass_count:], counts, counts[1:]), 1):
    wall = seconds(stopped) - seconds(started)
    if wall < 0:
        wall += 86400
    instructions = after - before
    if not 0.98 * expected <= instructions <= 1.02 * expected:
        raise SystemExit(f"pass {index}: expected about {expected:.0f} instructions, got {instructions}")
    mips = instructions / wall / 1_000_000
    samples.append({"pass": index, "guest_instructions": instructions,
                    "wall_seconds": wall, "throughput_mips": mips,
                    "rtx_at_96_mhz": mips / 96})

median_rtx = statistics.median(sample["rtx_at_96_mhz"] for sample in samples)
minimum_rtx = min(sample["rtx_at_96_mhz"] for sample in samples)
if median_rtx < 1.0 or minimum_rtx < 1.0:
    raise SystemExit(f"real-time floor failed: median={median_rtx:.6f} min={minimum_rtx:.6f}")

report = {
    "benchmark": "Renode SPIKE Prime STM32F413VG active-loop throughput",
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "advance_immediately": True,
    "platform_performance_mips": 96,
    "warmup_virtual_seconds": interval,
    "pass_virtual_seconds": interval,
    "passes": samples,
    "uart_smoke": "SPIKE\n",
    "brick_state_proof_run": brick_state_run,
    "summary": {
        "median_mips": statistics.median(sample["throughput_mips"] for sample in samples),
        "median_rtx_at_96_mhz": median_rtx,
        "min_rtx_at_96_mhz": minimum_rtx,
        "max_rtx_at_96_mhz": max(sample["rtx_at_96_mhz"] for sample in samples),
    },
    "method": ("One process; pacing disabled; one warm-up then fixed virtual-time "
               "passes; exact non-idle ExecutedInstructions deltas divided by "
               "start/pause wall intervals."),
}
result_path.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY

