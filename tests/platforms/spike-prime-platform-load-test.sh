#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
renode_dll=${RENODE_DLL:-"$repo_root/output/bin/Release/Renode.dll"}
log=$(mktemp)
trap 'rm -f "$log"' EXIT

test -f "$renode_dll"
cd "$repo_root"
timeout --kill-after=5s 120s dotnet "$renode_dll" --disable-xwt --plain \
  -e 'mach create; machine LoadPlatformDescription @platforms/boards/spike-prime.repl; peripherals; quit' \
  | tee "$log"

grep -Fq 'adc1' "$log"
grep -Fq 'bluetoothButton' "$log"
grep -Fq 'centerButton' "$log"
grep -Fq 'display' "$log"
grep -Fq 'speaker' "$log"
grep -Fq 'timer12' "$log"
