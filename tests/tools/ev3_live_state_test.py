#!/usr/bin/env python3
"""Bounded real Renode/IronPython EV3 observer and input integration proof."""
import argparse
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from spike_state_bridge import parse_line


def monitor_path(path):
    value = str(pathlib.Path(path).resolve())
    if any(char in value for char in '\n\r\t;"'):
        raise ValueError("unsafe monitor path")
    return '@' + value.replace(' ', '\\ ')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--renode", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--initial-payload", help="Optional source-built display initialization guest")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-motors", default="")
    args = parser.parse_args()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    commands = ["mach create", "machine LoadPlatformDescription " + monitor_path(args.platform)]
    if args.initial_payload:
        commands += ["sysbus LoadELF " + monitor_path(args.initial_payload),
                     "emulation RunFor \"0.01\"",
                     # Loading a second ELF at the same RAM address is not a
                     # CPU reset. Keep panel state, but discard the old guest's
                     # translated code/CPU state and restore the platform's
                     # high-vector handoff before starting the motor guest.
                     "cpu Reset", "cpu ModelID 0x41069265",
                     "cpu ExceptionVectorAddress 0xffff0000",
                     "sysbus WriteDoubleWord 0x01f0e008 0", "aintc Reset"]
    commands += ["sysbus LoadELF " + monitor_path(args.payload), "emulation RunFor \"0.1\"",
        "include " + monitor_path(ROOT / "scripts/spike-state-server.py"),
        'spike_state_start "127.0.0.1" %d %s' % (port, monitor_path(ROOT / "contracts/brick-state/renode-ev3.example.json"))]
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen([args.renode, "--disable-gui", "--plain", "--console"] +
            [part for command in commands for part in ("-e", command)], stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    stream = socket.create_connection(("127.0.0.1", port), timeout=1)
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Renode state server did not start")
                    time.sleep(0.05)
            with stream:
                stream.settimeout(5)
                reader = stream.makefile("rb")
                last_seq = -1

                def receive():
                    nonlocal last_seq
                    line = reader.readline(262145)
                    if not line.endswith(b"\n") or len(line) > 262144:
                        raise RuntimeError("state stream EOF or oversized frame")
                    frame = parse_line(line)
                    if frame["type"] == "snapshot":
                        if frame["seq"] <= last_seq:
                            raise RuntimeError("state sequence regression")
                        last_seq = frame["seq"]
                    return frame

                def command(request, name, arguments, accepted=True, expected=None):
                    stream.sendall((json.dumps({"schemaVersion":1,"type":"command","requestId":request,
                        "expectedSeq":last_seq if expected is None else expected,"command":name,"arguments":arguments}) + "\n").encode())
                    result = receive()
                    if result["type"] != "result" or result["requestId"] != request or result["accepted"] != accepted:
                        raise RuntimeError("unexpected command result")
                    return receive()

                initial = receive()
                assert initial["target"]["board"] == "ev3"
                assert initial["display"]["width"] == 178 and initial["display"]["height"] == 128
                assert initial["display"]["pixels"][:2] == [0, 255]
                assert len(initial["sensors"][0]["values"]["channels"]) == 16
                if args.expected_motors:
                    assert {motor["port"] for motor in initial["motors"]} == set(args.expected_motors)
                    assert all(motor["emittedEdges"] > 0 for motor in initial["motors"])
                pressed = command("press", "ev3.button.set", {"button":"center","pressed":True})
                assert pressed["buttons"]["center"] is True
                released = command("release", "ev3.button.set", {"button":"center","pressed":False})
                assert released["buttons"]["center"] is False
                analog = command("adc", "ev3.analog.set-channel", {"channel":3,"value":777})
                assert analog["sensors"][0]["values"]["channels"][3] == 777
                rejected = command("invalid", "ev3.analog.set-channel", {"channel":16,"value":1023}, False)
                assert rejected["sensors"][0]["values"]["channels"][3] == 777
                command("adc", "ev3.analog.set-channel", {"channel":3,"value":1}, False)
                command("stale", "state.sample", {}, False, expected=0)
                final = command("refresh", "state.sample", {})
                pathlib.Path(args.receipt).write_text(json.dumps({"schema":1,"target":"ev3",
                    "initial":initial,"final":final,"proofs":["real-IronPython-model-observation",
                    "178x128-frame","button-press-release","ADC-input","bounds","replay","stale-seq"],
                    "result":"pass"}, sort_keys=True) + "\n")
                print("EV3 LIVE MODEL STATE OK")
        except Exception:
            log.seek(0)
            sys.stderr.write(log.read().decode("utf-8", "replace")[-16000:])
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__": main()
