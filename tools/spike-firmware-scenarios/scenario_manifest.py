#!/usr/bin/env python3
"""Prepare and verify local, opaque firmware scenario inputs."""

import argparse
import hashlib
import json
import pathlib
import shutil
import sys

SCHEMA = "brickwright.renode.scenario-input/v1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG_PATH = pathlib.Path(__file__).with_name("scenarios-v1.json")
DEFAULT_IMAGE_ROOT = ROOT / ".local" / "spike-firmware-scenarios"


class ManifestError(ValueError):
    pass


def catalog():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if data.get("schema") != "brickwright.renode.scenarios/v1":
        raise ManifestError("unsupported scenario catalog schema")
    return data


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def parse_artifact(text):
    try:
        name, fmt, address, source = text.split("=", 3)
    except ValueError as error:
        raise ManifestError("artifact must be NAME=FORMAT=LOAD_ADDRESS=PATH") from error
    if fmt not in ("raw", "elf"):
        raise ManifestError(f"unsupported artifact format: {fmt}")
    try:
        parsed_address = int(address, 0)
    except ValueError as error:
        raise ManifestError(f"invalid load address: {address}") from error
    if not 0x08000000 <= parsed_address < 0x08200000:
        raise ManifestError("load address is outside the supported STM32 flash window")
    source_path = pathlib.Path(source).resolve()
    if not source_path.is_file():
        raise ManifestError(f"artifact does not exist: {source}")
    if fmt == "elf":
        with source_path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ManifestError(f"ELF artifact has no ELF magic: {name}")
    return name, fmt, parsed_address, source_path


def prepare(args):
    definitions = catalog()["targets"]
    if args.target not in definitions:
        raise ManifestError(f"unknown target: {args.target}")
    parsed = [parse_artifact(item) for item in args.artifact]
    names = [item[0] for item in parsed]
    expected = definitions[args.target]["artifacts"]
    if names != expected:
        raise ManifestError(f"target requires artifacts in this order: {', '.join(expected)}")
    destination = pathlib.Path(args.root).resolve() / args.target
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for name, fmt, address, source in parsed:
        output = destination / f"{name}.{fmt}"
        shutil.copyfile(source, output)
        output.chmod(0o600)
        records.append({
            "name": name,
            "file": output.name,
            "format": fmt,
            "load_address": f"0x{address:08x}",
            "size": output.stat().st_size,
            "sha256": digest(output),
        })
    manifest = {"schema": SCHEMA, "target": args.target, "artifacts": records}
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    print(manifest_path)


def verify(target, root):
    definitions = catalog()["targets"]
    if target not in definitions:
        raise ManifestError(f"unknown target: {target}")
    directory = pathlib.Path(root).resolve() / target
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA or data.get("target") != target:
        raise ManifestError("manifest schema or target mismatch")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        raise ManifestError("artifacts must be a list")
    names = [item.get("name") for item in artifacts if isinstance(item, dict)]
    if names != definitions[target]["artifacts"]:
        raise ManifestError("artifact set or order does not match the scenario catalog")
    for item in artifacts:
        if set(item) != {"name", "file", "format", "load_address", "size", "sha256"}:
            raise ManifestError(f"invalid artifact fields: {item.get('name', '<unknown>')}")
        filename = item["file"]
        if pathlib.PurePath(filename).name != filename:
            raise ManifestError("artifact file must be a basename")
        path = directory / filename
        if not path.is_file():
            raise ManifestError(f"missing artifact: {filename}")
        if path.stat().st_size != item["size"]:
            raise ManifestError(f"size mismatch: {filename}")
        if digest(path) != item["sha256"]:
            raise ManifestError(f"SHA-256 mismatch: {filename}")
        if item["format"] not in ("raw", "elf"):
            raise ManifestError(f"invalid format: {filename}")
        address = int(item["load_address"], 0)
        if not 0x08000000 <= address < 0x08200000:
            raise ManifestError(f"invalid load address: {filename}")
        if item["format"] == "raw" and address + item["size"] > 0x08200000:
            raise ManifestError(f"raw artifact exceeds the supported flash window: {filename}")
    return {"definition": definitions[target], "manifest": data, "directory": str(directory)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_IMAGE_ROOT))
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("target")
    prepare_parser.add_argument("--artifact", action="append", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("target")
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.add_argument("--execution-json", action="store_true")
    list_parser = commands.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "verify":
            result = verify(args.target, args.root)
            if result is None:
                print(f"SKIP: no local manifest for {args.target}")
                return 77
            if args.execution_json:
                public = {
                    "board": result["definition"]["board"],
                    "target": args.target,
                    "artifacts": [{key: item[key] for key in ("name", "file", "format", "load_address")}
                                  for item in result["manifest"]["artifacts"]],
                }
                print(json.dumps(public, sort_keys=True))
            else:
                print(json.dumps(result, sort_keys=True) if args.json else f"verified: {args.target}")
        else:
            definitions = catalog()["targets"]
            print(json.dumps(definitions, indent=2) if args.json else "\n".join(definitions))
    except (ManifestError, json.JSONDecodeError, KeyError, TypeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
