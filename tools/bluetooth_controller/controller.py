"""Transport-neutral Bluetooth controller API.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .protocols import L2capRouter

FrameSink = Callable[[bytes], None]


@dataclass(frozen=True)
class ControllerConfig:
    address: bytes = bytes.fromhex("060504030201")
    acknowledge_vendor_commands: bool = False

    def __post_init__(self) -> None:
        if len(self.address) != 6:
            raise ValueError("Bluetooth address must contain exactly six bytes")


class BluetoothController:
    """Protocol core; transports only call ``feed`` and consume emitted frames."""

    def __init__(self, sink: FrameSink, config: ControllerConfig | None = None) -> None:
        self.sink = sink
        self.config = config or ControllerConfig()
        self.l2cap = L2capRouter()

    def feed(self, data: bytes) -> None:
        raise NotImplementedError("H4 parsing is implemented in the next checkpoint")
