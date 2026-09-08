#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
test_root=$(mktemp -d)
log="$test_root/renode.log"
trap 'rm -rf "$test_root"' EXIT

test -f "$repo_root/output/bin/Release/Renode.dll"
cd "$repo_root"

# The generic STM32F4 platform fetches an SVD used only for monitor register
# names. Build an otherwise byte-for-byte derived topology without that remote
# debug resource, so this gate remains offline and cannot touch firmware.
mkdir -p "$test_root/platforms/boards" "$test_root/platforms/cpus"
cp platforms/boards/spike-prime.repl "$test_root/platforms/boards/"
cp platforms/boards/spike-prime-brick-devices.repl "$test_root/platforms/boards/"
sed '/^[[:space:]]*ApplySVD @https:\/\/dl\.antmicro\.com\/projects\/renode\/svd\/STM32F40x\.svd\.gz$/d' \
  platforms/cpus/stm32f4.repl >"$test_root/platforms/cpus/stm32f4.repl"
test "$(wc -l <platforms/cpus/stm32f4.repl)" -eq "$(( $(wc -l <"$test_root/platforms/cpus/stm32f4.repl") + 1 ))"
! grep -R -E 'https?://|ApplySVD' "$test_root/platforms"

timeout --kill-after=5s 30s dotnet output/bin/Release/Renode.dll \
  --disable-xwt --plain -e 'mach create' -e 'quit'

timeout --kill-after=5s 120s dotnet output/bin/Release/Renode.dll \
  --disable-xwt --plain \
  -e 'mach create' \
  -e "machine LoadPlatformDescription @$test_root/platforms/boards/spike-prime.repl" \
  -e 'peripherals' \
  -e 'quit' | tee "$log"

grep -Fq 'adc1' "$log"
grep -Fq 'bluetoothButton' "$log"
grep -Fq 'centerButton' "$log"
grep -Fq 'display' "$log"
grep -Fq 'speaker' "$log"
grep -Fq 'timer12' "$log"
