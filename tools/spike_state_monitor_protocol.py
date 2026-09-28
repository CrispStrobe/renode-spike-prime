"""Python 2/3-compatible validation for the Renode monitor socket service."""

import re

try:
    string_types = (basestring,)
    integer_types = (int, long)
except NameError:
    string_types = (str,)
    integer_types = (int,)

FIRMWARE_BY_BOARD = {
    "spike-prime": ("lego-prime-v2", "lego-prime-v3", "pybricks-prime",
                    "spike-nx", "brickwright-nuttx"),
    "spike-essential": ("lego-essential", "pybricks-essential"),
}


def validate_config(config):
    if not isinstance(config, dict) or not isinstance(config.get("identity"), dict):
        raise ValueError("config and identity must be objects")
    if not isinstance(config.get("paths"), dict):
        raise ValueError("paths must be an object")
    identity = config["identity"]
    board, firmware = identity.get("board"), identity.get("firmware")
    if firmware not in FIRMWARE_BY_BOARD.get(board, ()):
        raise ValueError("unsupported board/firmware identity")
    transport = identity.get("transport")
    if not isinstance(transport, string_types) or not transport:
        raise ValueError("transport must be a nonempty string")
    if "imageSha256" not in identity:
        raise ValueError("imageSha256 is required")
    image_hash = identity["imageSha256"]
    if image_hash is not None and (not isinstance(image_hash, string_types) or
                                   re.match(r"^[0-9a-f]{64}$", image_hash) is None):
        raise ValueError("imageSha256 must be null or lowercase SHA-256")
    return config


def validate_command(command):
    if not isinstance(command, dict) or command.get("schemaVersion") != 1 or command.get("type") != "command":
        raise ValueError("invalid command envelope")
    request = command.get("requestId")
    name = command.get("command")
    arguments = command.get("arguments")
    if not isinstance(request, string_types) or not request or len(request) > 128:
        raise ValueError("invalid requestId")
    if not isinstance(name, string_types) or not name or len(name) > 64:
        raise ValueError("invalid command")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    if "expectedSeq" in command:
        expected = command["expectedSeq"]
        if (not isinstance(expected, integer_types) or isinstance(expected, bool) or
                expected < 0):
            raise ValueError("invalid expectedSeq")
    return command


def split_frames(pending, chunk, line_limit, read_limit, max_records=256):
    """Return complete records and remainder without treating a batch as a line."""
    if len(chunk.encode("utf-8")) > read_limit:
        raise ValueError("read exceeds configured limit")
    combined = pending + chunk
    parts = combined.split("\n")
    remainder = parts.pop()
    if len(parts) > max_records:
        raise ValueError("read contains too many records")
    for line in parts:
        if not line or "\r" in line or len(line.encode("utf-8")) > line_limit:
            raise ValueError("invalid framed line")
    if len(remainder.encode("utf-8")) > line_limit:
        raise ValueError("partial line exceeds configured limit")
    return parts, remainder
