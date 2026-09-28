#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 {official|pybricks} IMAGE {raw|elf} VECTOR_ADDRESS" >&2
    exit 2
}

[[ $# -eq 4 ]] || usage
kind=$1
source_image=$2
format=$3
load_address=${4:-}

[[ $kind == official || $kind == pybricks ]] || usage
[[ $format == raw || $format == elf ]] || usage
[[ -f $source_image ]] || { echo "image not found: $source_image" >&2; exit 1; }

[[ $load_address =~ ^0x[0-9a-fA-F]+$ ]] || usage
vector_address=$((load_address))
(( vector_address >= 0x08000000 && vector_address < 0x08100000 )) || {
    echo "vector address is outside verified Essential internal flash" >&2
    exit 1
}
if [[ $format == elf ]]; then
    elf_magic=$(od -An -tx1 -N4 "$source_image" | tr -d ' \n')
    [[ $elf_magic == 7f454c46 ]] || { echo "ELF input has no ELF magic" >&2; exit 1; }
fi

size=$(stat -c %s "$source_image")
if [[ $format == raw ]]; then
    start=$((load_address))
    end=$((start + size))
    (( start >= 0x08000000 && end <= 0x08100000 )) || {
        echo "raw image exceeds verified Essential internal flash window" >&2
        exit 1
    }
fi

repo_root=$(git rev-parse --show-toplevel)
image_root=${SPIKE_ESSENTIAL_IMAGE_ROOT:-$repo_root/.local/spike-essential-images}
target_dir="$image_root/$kind"
mkdir -p "$target_dir"
install -m 600 "$source_image" "$target_dir/image.$format"
sha256=$(sha256sum "$target_dir/image.$format" | awk '{print $1}')
address_json="\"$load_address\""
printf '{\n  "kind": "%s",\n  "format": "%s",\n  "load_address": %s,\n  "sha256": "%s",\n  "size": %s\n}\n' \
    "$kind" "$format" "$address_json" "$sha256" "$size" > "$target_dir/manifest.json"
echo "$target_dir/manifest.json"
