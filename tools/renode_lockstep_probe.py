# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""IronPython monitor include: wall time of RunFor quanta (Robot Lab R13-M).

``bw_runfor_probe <quantumUs> <count> <result.json>`` runs ``count`` quanta on
the monitor thread and appends one JSON line: wall ms per call (median, p90),
virtual seconds per wall second and executed instructions per virtual second.
Measurement only; nothing here is part of the state service.
"""
import json
from System.Diagnostics import Stopwatch
from System import UInt64
from Antmicro.Renode.Time import TimeInterval


def _instructions():
    try:
        return int(monitor.Machine["sysbus.cpu"].ExecutedInstructions)
    except Exception:
        return -1


def mc_bw_runfor_probe(quantum_us, count, result_path, label=""):
    quantum_us, count = int(quantum_us), int(count)
    emulation = emulationManager.CurrentEmulation
    clock = lambda: int(emulation.MasterTimeSource.ElapsedVirtualTime.TotalNanoseconds)
    start_ns, start_ins = clock(), _instructions()
    walls = []
    for _ in range(count):
        watch = Stopwatch.StartNew()
        emulation.RunFor(TimeInterval.FromMicroseconds(UInt64(quantum_us)))
        walls.append(watch.Elapsed.TotalMilliseconds)
    elapsed_ns, ins = clock() - start_ns, _instructions() - start_ins
    ordered = sorted(walls)
    record = {"label": str(label), "quantumUs": quantum_us, "count": count,
              "exactClock": elapsed_ns == quantum_us * 1000 * count,
              "medianMs": round(ordered[len(ordered) // 2], 3),
              "p90Ms": round(ordered[max(0, int(0.9 * len(ordered)) - 1)], 3),
              "virtualPerWall": round(elapsed_ns / 1e6 / sum(walls), 4),
              "instructionsPerVirtualSecond": int(ins / (elapsed_ns / 1e9)) if ins >= 0 else None}
    with open(str(result_path), "a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True))
