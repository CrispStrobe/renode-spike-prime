"""MIT-licensed, Python 2/3-compatible EV3 public-model observation.

No monitor evaluation, guest memory fabrication, or physical robot transport.
The supplied resolver is the already constrained model-path resolver.
"""

BUTTONS = ("center", "left", "back", "right", "down", "up")
LEDS = ("leftGreen", "leftRed", "rightGreen", "rightRed")

try:
    integer_types = (int, long)
except NameError:
    integer_types = (int,)


def bounded(arguments, name, minimum, maximum):
    value = arguments.get(name)
    if not isinstance(value, integer_types) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(name + " is outside the supported range")
    return value


def observe(config, resolve, seq, clock_ns, generation):
    paths = config["paths"]
    missing = []

    def optional(role):
        if role not in paths:
            missing.append(role)
            return None
        try:
            return resolve(paths[role])
        except (KeyError, IndexError):
            missing.append(role)
            return None

    buttons, leds = {}, {}
    for name in BUTTONS:
        model = optional(name + "Button")
        buttons[name] = bool(model.Pressed) if model is not None else None
    for name in LEDS:
        model = optional(name + "Led")
        leds[name] = bool(model.State) if model is not None else None
    panel = optional("display")
    display = {"width": 0, "height": 0, "pixels": [], "semantics": "unavailable"}
    if panel is not None:
        pixels = [int(value) for value in panel.GetFrameSnapshot()]
        if len(pixels) != 178 * 128 or any(value < 0 or value > 255 for value in pixels):
            raise ValueError("EV3 framebuffer is malformed")
        display = {"width": 178, "height": 128, "pixels": pixels,
                   "semantics": "grayscale-8bit", "enabled": bool(panel.DisplayEnabled)}
    adc = optional("adc")
    sensors = [] if adc is None else [{"port": "adc", "kind": "raw-analog",
        "values": {"channels": [int(adc.GetChannelValue(channel)) for channel in range(16)]}}]
    motors, ports = [], []
    for port in "ABCD":
        motor = optional("motor" + port)
        ports.append({"id": port, "attached": motor is not None,
                      "kind": "modeled-motor" if motor is not None else None})
        if motor is not None:
            motors.append({"port": port, "state": str(motor.State),
                "direction": int(motor.Direction), "dutyCycle": float(motor.DutyCycle),
                "tachometerCount": int(motor.TachometerCount), "emittedEdges": int(motor.EmittedEdges)})
    identity = dict(config["identity"])
    identity["capabilities"] = ["model-observation", "bounded-command-dispatch"]
    identity["limitations"] = ["simulation only; no physical robot transport",
        "raw ADC channels are not decoded EV3 sensor protocols",
        "motor state is electrical model output, not mechanical physics",
        "audio, battery, IMU and Bluetooth unavailable"]
    if missing:
        identity["limitations"].append("unavailable models: " + ", ".join(missing))
    return {"schemaVersion": 1, "type": "snapshot", "seq": seq, "clockNs": clock_ns,
        "target": identity, "lifecycle": {"phase": "ready", "generation": 0,
        "connectionGeneration": generation}, "ports": ports, "motors": motors, "sensors": sensors,
        "display": display, "buttons": buttons, "battery": {"available": False},
        "power": {"state": "modeled", "leds": leds}, "imu": {"available": False},
        "audio": {"active": False, "available": False}, "storage": {"ready": False},
        "bluetooth": {"state": "unavailable", "transport": "none"}}


def dispatch(config, resolve, command):
    name, args = command["command"], command["arguments"]
    if name == "state.sample":
        if args:
            raise ValueError("state.sample takes no arguments")
        return
    if name == "ev3.button.set":
        button, pressed = args.get("button"), args.get("pressed")
        if button not in BUTTONS or not isinstance(pressed, bool) or set(args) != set(("button", "pressed")):
            raise ValueError("invalid EV3 button input")
        model = resolve(config["paths"][button + "Button"])
        (model.Press if pressed else model.Release)()
    elif name == "ev3.analog.set-channel":
        if set(args) != set(("channel", "value")):
            raise ValueError("invalid EV3 analog input")
        channel = bounded(args, "channel", 0, 15)
        value = bounded(args, "value", 0, 1023)
        resolve(config["paths"]["adc"]).SetChannelValue(channel, value)
    else:
        raise ValueError("unknown command")
