#!/bin/sh
# Re-derive the SoftDevice interface facts nrf-softdevice-hle uses, from the
# BSD-3 (no chip clause) S130 v2 headers in lancaster-university/nrf51-sdk
# v2.2.0+mb4 — the SDK the micro:bit DAL itself builds against. Nothing from
# those headers is committed: this script clones them into a temp dir,
# evaluates enums/defines (enums.py) and measures struct offsets with a probe
# compiled for Cortex-M0 (layout.c, dumplayout.py). Output: s130-facts.json,
# s130-layout.json, compared by hand/CI against crates/nrf-softdevice-hle/src/facts.rs.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
w=$(mktemp -d)
git clone -q --depth 1 --branch v2.2.0+mb4 https://github.com/lancaster-university/nrf51-sdk "$w/sdk"
H="$w/sdk/source/nordic_sdk/components/softdevice/s130/headers"
head -20 "$H/ble_ranges.h" | grep -q "Redistribution and use in source and binary forms" || { echo "licence header changed"; exit 1; }
if grep -qi "integrated circuit" "$H"/*.h; then echo "a chip clause appeared in the headers: stop"; exit 1; fi
cd "$w"
python3 "$here/enums.py" "$H"
mkdir -p stub && cp "$here/nrf_stub.h" stub/nrf.h
arm-none-eabi-gcc -mcpu=cortex-m0 -mthumb -Os -c -I stub -I "$H" "$here/layout.c" -o layout.o
python3 "$here/dumplayout.py" > /dev/null
cp s130-facts.json s130-layout.json "$here/../facts-out/" 2>/dev/null || { mkdir -p "$here/../facts-out"; cp s130-facts.json s130-layout.json "$here/../facts-out/"; }
echo "facts in $here/../facts-out"
