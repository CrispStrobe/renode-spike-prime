#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
fixture_dir=$(mktemp -d)
printf '\x00\x00\x05\x20\x01\x81\x00\x08' > "$fixture_dir/image.bin"
export SPIKE_ESSENTIAL_IMAGE_ROOT="$fixture_dir/output"
manifest=$(tools/spike-essential/prepare-local-image.sh pybricks "$fixture_dir/image.bin" raw 0x08008000)
expected=$(sha256sum "$fixture_dir/image.bin" | awk '{print $1}')
grep -Fq "\"sha256\": \"$expected\"" "$manifest"
grep -Fq '"load_address": "0x08008000"' "$manifest"
cmp "$fixture_dir/image.bin" "$(dirname "$manifest")/image.raw"

if tools/spike-essential/prepare-local-image.sh prime "$fixture_dir/image.bin" raw 0x08008000 >/dev/null 2>&1; then
    echo "loader accepted a non-Essential target" >&2
    exit 1
fi

if tools/spike-essential/prepare-local-image.sh official "$fixture_dir/image.bin" raw 0x08100000 >/dev/null 2>&1; then
    echo "loader accepted an out-of-range image" >&2
    exit 1
fi
