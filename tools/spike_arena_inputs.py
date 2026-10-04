# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bounded synthetic arena inputs for public Renode LPF2 model interfaces."""
try:
    integer_types = (int, long)
except NameError:
    integer_types = (int,)

PRIME_HUB_PATHS = {
    "leftButton": "machine:sysbus.leftButton",
    "centerButton": "machine:sysbus.centerButton",
    "rightButton": "machine:sysbus.rightButton",
    "bluetoothButton": "machine:sysbus.bluetoothButton",
    "imu": "machine:sysbus.i2c2.imu",
    "speaker": "machine:sysbus.speaker",
    "display": "machine:sysbus.spi1.display",
}
BUTTON_ROLES = (("left", "leftButton"), ("center", "centerButton"),
                ("right", "rightButton"), ("bluetooth", "bluetoothButton"))


def resolve_prime_hub_models(paths, resolve):
    """Only the retained Prime overlay's closed model paths are admitted."""
    if any(paths.get(role) != path for role, path in PRIME_HUB_PATHS.items()):
        raise ValueError("Prime hub model paths unavailable")
    try:
        models = {role: resolve(path) for role, path in PRIME_HUB_PATHS.items()}
        _validate_prime_hub_models(models)
        return models
    except (KeyError, AttributeError, TypeError):
        raise ValueError("Prime hub model unavailable")


def _validate_prime_hub_models(models):
    for _, role in BUTTON_ROLES:
        button = models.get(role)
        if not hasattr(button, "Pressed") or not callable(getattr(button, "Press", None)) or not callable(getattr(button, "Release", None)):
            raise ValueError("Prime button model unavailable")
    imu, speaker, display = (models.get(role) for role in ("imu", "speaker", "display"))
    if not callable(getattr(imu, "FeedSample", None)) or not hasattr(imu, "RegisterSnapshot") or len(imu.RegisterSnapshot) < 0x2e:
        raise ValueError("Prime IMU model unavailable")
    if any(not hasattr(speaker, name) for name in ("Enabled", "LastSample", "TotalBytes", "DroppedBytes", "DisabledBytes", "BufferedBytes")):
        raise ValueError("Prime speaker model unavailable")
    if not hasattr(display, "Matrix") or len(display.Matrix) != 25:
        raise ValueError("Prime display model unavailable")


def observe_prime_hub(models):
    """Read register snapshots and counters without consuming peripheral data."""
    registers = models["imu"].RegisterSnapshot
    def signed(offset):
        value = int(registers[offset]) | (int(registers[offset + 1]) << 8)
        return value - 65536 if value >= 32768 else value
    speaker = models["speaker"]
    return ({name: bool(models[role].Pressed) for name, role in BUTTON_ROLES},
            {"available": True, "semantics": "signed-16bit-raw",
             "temperature": signed(0x20), "angularRate": [signed(i) for i in (0x22, 0x24, 0x26)],
             "acceleration": [signed(i) for i in (0x28, 0x2a, 0x2c)]},
            {"available": True, "enabled": bool(speaker.Enabled),
             "active": bool(speaker.Enabled and speaker.BufferedBytes > 0),
             "bufferedBytes": int(speaker.BufferedBytes),
             "pcm8": {"lastSample": int(speaker.LastSample), "totalBytes": int(speaker.TotalBytes),
             "droppedBytes": int(speaker.DroppedBytes), "disabledBytes": int(speaker.DisabledBytes),
             "bufferedBytes": int(speaker.BufferedBytes)}})


def validate_arena_inputs(arguments):
    """Bounded semantic inputs only: no model paths, monitor text or firmware bytes."""
    if not isinstance(arguments, dict) or set(arguments) not in (set(("sensors", "loads")), set(("sensors", "loads", "hub"))):
        raise ValueError("arena inputs must contain sensors, loads and optional hub only")
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
    if "hub" in arguments:
        hub = arguments["hub"]
        if not isinstance(hub, dict) or set(hub) != set(("buttons", "imuRaw")):
            raise ValueError("invalid Prime hub input fields")
        buttons, imu = hub["buttons"], hub["imuRaw"]
        if not isinstance(buttons, dict) or set(buttons) != set(name for name, _ in BUTTON_ROLES) or any(not isinstance(value, bool) for value in buttons.values()):
            raise ValueError("Prime buttons must be four booleans")
        if not isinstance(imu, dict) or set(imu) != set(("temperature", "angularRate", "acceleration")):
            raise ValueError("invalid Prime IMU fields")
        for name in ("angularRate", "acceleration"):
            if not isinstance(imu[name], list) or len(imu[name]) != 3:
                raise ValueError("Prime IMU vectors must contain three signed integers")
        for value in [imu["temperature"]] + imu["angularRate"] + imu["acceleration"]:
            if not isinstance(value, integer_types) or isinstance(value, bool) or not -32768 <= value <= 32767:
                raise ValueError("Prime IMU value outside signed 16-bit range")
    return arguments


def apply_arena_inputs(arguments, get_device, hub_models=None):
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
    if "hub" in inputs:
        if hub_models is None:
            raise ValueError("Prime hub input unavailable")
        _validate_prime_hub_models(hub_models)
        hub = inputs["hub"]
        for name, role in BUTTON_ROLES:
            button = hub_models.get(role)
            fn = getattr(button, "Press" if hub["buttons"][name] else "Release", None)
            if not callable(fn):
                raise ValueError("Prime button model unavailable")
            pending.append((fn, ()))
        fn = getattr(hub_models.get("imu"), "FeedSample", None)
        if not callable(fn):
            raise ValueError("Prime IMU model unavailable")
        imu = hub["imuRaw"]
        pending.append((fn, tuple([imu["temperature"]] + imu["angularRate"] + imu["acceleration"])))
    # Validate and resolve the complete frame before changing any model.
    for fn, args in pending:
        fn(*args)
