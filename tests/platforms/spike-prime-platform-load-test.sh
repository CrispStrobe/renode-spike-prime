#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
test_root=$(mktemp -d)
log="$test_root/renode.log"
marker="$test_root/platform-loaded"
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

cp tests/platforms/fixtures/probe-*.repl "$test_root/platforms/boards/"

timeout --kill-after=5s 30s dotnet output/bin/Release/Renode.dll \
  --disable-xwt --plain -e 'mach create' -e 'quit'

probe_failed=0
for probe in adc display audio; do
  probe_marker="$test_root/probe-$probe-loaded"
  probe_log="$test_root/probe-$probe.log"
  timeout --kill-after=5s 60s dotnet output/bin/Release/Renode.dll \
    --disable-xwt --plain \
    -e 'mach create' \
    -e "machine LoadPlatformDescription @$test_root/platforms/boards/probe-$probe.repl" \
    -e "python \"open(r'$probe_marker', 'w').write('loaded')\"" \
    -e 'quit' >"$probe_log" 2>&1 || true
  cat "$probe_log"
  if ! test -f "$probe_marker"; then
    echo "SPIKE Prime platform probe failed: $probe" >&2
    probe_failed=1
  fi
done
test "$probe_failed" -eq 0

dotnet output/bin/Release/Renode.dll \
  --disable-xwt --plain \
  -e 'mach create' \
  -e "machine LoadPlatformDescription @$test_root/platforms/boards/spike-prime.repl" \
  -e "python \"names = set(self.Machine.GetAllNames()); assert set(['adc1', 'bluetoothButton', 'centerButton', 'display', 'speaker', 'timer12']).issubset(names); open(r'$marker', 'w').write('loaded')\"" \
  -e 'quit' >"$log" 2>&1 &
renode_pid=$!

for _ in $(seq 1 300); do
  if test -f "$marker" || ! kill -0 "$renode_pid" 2>/dev/null; then
    break
  fi
  sleep 1
done

if kill -0 "$renode_pid" 2>/dev/null; then
  kill "$renode_pid"
fi
wait "$renode_pid" 2>/dev/null || true
cat "$log"
test "$(cat "$marker")" = loaded
