#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read CP11 guest register evidence through Renode's actual GDB server."""
import json
from pathlib import Path
import socket
import subprocess
import time


def receive_exact(connection, length):
    result = bytearray()
    while len(result) < length:
        value = connection.recv(length - len(result))
        if not value:
            raise RuntimeError("GDB disconnected")
        result.extend(value)
    return bytes(result)


def exchange(connection, command):
    encoded = command.encode("ascii")
    connection.sendall(b"$" + encoded + b"#" + f"{sum(encoded) & 255:02x}".encode())
    for _ in range(65536):
        if receive_exact(connection, 1) == b"$":
            break
    else:
        raise RuntimeError("GDB response marker exceeds limit")
    payload = bytearray()
    while True:
        value = receive_exact(connection, 1)
        if value == b"#":
            break
        payload.extend(value)
        if len(payload) > 65536:
            raise RuntimeError("GDB response payload exceeds limit")
    checksum = receive_exact(connection, 2)
    if checksum != f"{sum(payload) & 255:02x}".encode():
        raise RuntimeError("GDB packet checksum mismatch")
    connection.sendall(b"+")
    return payload.decode("ascii")


def qualify(name, commands, registers):
    with socket.socket() as allocator:
        allocator.bind(("127.0.0.1", 0))
        port = allocator.getsockname()[1]
    log_path = Path(f"/tmp/ev3-{name}-gdb-monitor.log")
    uart_path = Path(f"/tmp/ev3-{name}-gdb-uart.log")
    uart_path.unlink(missing_ok=True)
    setup = (
        "mach create; machine LoadPlatformDescription @platforms/boards/lego-ev3.repl; "
        f"sysbus LoadELF @tests/platforms/LEGO_EV3/am1808-{name}-smoke.elf; "
        f"uart1 CreateFileBackend @{uart_path} true; {commands}; "
        f"machine StartGdbServer {port} false"
    )
    with log_path.open("w") as log:
        process = subprocess.Popen(
            ["dotnet", "output/bin/Release/Renode.dll", "--disable-gui", "--plain", "-e", setup],
            stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=2)
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError(f"Renode GDB startup failed: {log_path.read_text()}")
                    time.sleep(0.1)
            with connection:
                connection.settimeout(5)
                assert exchange(connection, "?").startswith(("S", "T"))
                values = {}
                for label, address, mask, expected in registers:
                    response = exchange(connection, f"m{address:x},4")
                    if len(response) != 8:
                        raise RuntimeError(f"Invalid four-byte GDB memory response for {label}: {response!r}")
                    value = int.from_bytes(bytes.fromhex(response), "little")
                    assert value & mask == expected, (label, hex(value), hex(expected))
                    values[label] = f"0x{value:08x}"
            return {"uart": uart_path.read_text().strip(), "gdb_mmio": values}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    gpio = qualify("gpio", 'emulation RunFor "0.002"; sysbus.gpio.centerButton Press; emulation RunFor "0.01"', [
        ("GPIO_DIR67", 0x01E26088, 0x80, 0),
        ("GPIO_OUT67", 0x01E2608C, 0x80, 0x80),
        ("GPIO_IN01", 0x01E26020, 0x20000000, 0x20000000),
        ("GPIO_INTSTAT01", 0x01E26034, 0x20000000, 0),
    ])
    display = qualify("spi-display", 'emulation RunFor "0.02"', [
        ("GPIO_DIR23", 0x01E26038, 0x1800, 0),
        ("GPIO_OUT23", 0x01E2603C, 0x1800, 0x1000),
        ("GPIO_DIR45", 0x01E26060, 0x10000, 0),
        ("SPI_GCR1", 0x01F0E004, 0xFFFFFFFF, 0x01000003),
        ("SPI_FMT0", 0x01F0E050, 0xFFFFFFFF, 0x00000E08),
    ])
    assert gpio["uart"] == "EV3 GPIO BUTTON LED OK", gpio
    assert display["uart"] == "EV3 SPI DISPLAY IRQ OK", display
    receipt = {"schema": "brickwright.ev3.am1808-debugger.v1", "gpio": gpio, "display": display}
    output = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    Path("/tmp/ev3-cp11-debugger-receipt.json").write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
