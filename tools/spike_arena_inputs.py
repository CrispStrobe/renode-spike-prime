# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bounded synthetic arena inputs for public Renode LPF2 model interfaces."""
try:
    integer_types = (int, long)
except NameError:
    integer_types = (int,)


def validate_arena_inputs(arguments):
    """Bounded semantic inputs only: no model paths, monitor text or firmware bytes."""
    if not isinstance(arguments, dict) or set(arguments) != set(("sensors", "loads")):
        raise ValueError("arena inputs must contain sensors and loads only")
    sensors, loads = arguments["sensors"], arguments["loads"]
    if not isinstance(sensors, list) or not isinstance(loads, list) or len(sensors) > 6 or len(loads) > 6:
        raise ValueError("arena inputs support at most six sensors and six loads")
    ports = set()
    fields = {"distance": {"distanceMillimeters": (-1, 65535)},
              "color": {"colorId": (0, 255), "reflectionPercent": (0, 100), "ambientPercent": (0, 100)},
              "force": {"forcePercent": (0, 100), "pressed": None}}
    for item in sensors + loads:
        if not isinstance(item, dict):
            raise ValueError("arena input must be an object")
        port = item.get("port")
        if port not in ("A", "B", "C", "D", "E", "F") or port in ports:
            raise ValueError("arena ports must be unique A-F")
        ports.add(port)
    for item in sensors:
        if set(item) != set(("port", "kind", "values")) or item.get("kind") not in fields:
            raise ValueError("unsupported arena sensor")
        values, spec = item["values"], fields[item["kind"]]
        if not isinstance(values, dict) or set(values) != set(spec):
            raise ValueError("invalid arena sensor fields")
        for name, bounds in spec.items():
            value = values[name]
            if bounds is None:
                if not isinstance(value, bool):
                    raise ValueError("pressed must be boolean")
            elif not isinstance(value, integer_types) or isinstance(value, bool) or not bounds[0] <= value <= bounds[1]:
                raise ValueError("arena sensor value outside range")
    for item in loads:
        if set(item) != set(("port", "percent")) or not isinstance(item["percent"], integer_types) or isinstance(item["percent"], bool) or not 0 <= item["percent"] <= 100:
            raise ValueError("invalid arena motor load")
    return arguments


def apply_arena_inputs(arguments, get_device):
    inputs = validate_arena_inputs(arguments)
    pending = []
    for item in inputs["sensors"]:
        device = get_device(item["port"])
        values = item["values"]
        if item["kind"] == "distance" and hasattr(device, "SetDistance"):
            pending.append((device.SetDistance, (65535 if values["distanceMillimeters"] == -1 else values["distanceMillimeters"],)))
        elif item["kind"] == "color" and hasattr(device, "ColorId") and hasattr(device, "SetReading"):
            pending.append((device.SetReading, (values["colorId"], values["reflectionPercent"], values["ambientPercent"])))
        elif item["kind"] == "force" and hasattr(device, "ForcePercent") and hasattr(device, "SetReading"):
            pending.append((device.SetReading, (values["forcePercent"], values["pressed"])))
        else:
            raise ValueError("arena sensor model unavailable")
    for item in inputs["loads"]:
        device = get_device(item["port"])
        if not hasattr(device, "SetLoad"):
            raise ValueError("arena motor load model unavailable")
        pending.append((device.SetLoad, (item["percent"],)))
    # Validate and resolve the complete frame before changing any model.
    for fn, args in pending:
        fn(*args)
