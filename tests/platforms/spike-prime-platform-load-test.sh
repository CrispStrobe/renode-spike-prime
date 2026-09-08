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

cp tests/platforms/fixtures/probe-*.repl "$test_root/platforms/boards/"

timeout --kill-after=5s 30s dotnet output/bin/Release/Renode.dll \
  --disable-xwt --console --plain -e 'mach create; quit'

load_platform() {
  local name=$1
  local platform=$2
  local expected=$3
  local inspection=${4:-}
  local load_log="$test_root/$name.log"

  timeout --kill-after=5s 60s dotnet output/bin/Release/Renode.dll \
    --disable-xwt --console --plain \
    -e "mach create; machine LoadPlatformDescription @$platform; $inspection peripherals; quit" \
    >"$load_log" 2>&1
  cat "$load_log"
  ! grep -Fq 'Error E' "$load_log"
  ! grep -Fq 'There was an error executing command' "$load_log"
  grep -Fq "$expected" "$load_log"
}

probe_failed=0
for probe in adc display audio; do
  case "$probe" in
    adc) expected=adc1 ;;
    display) expected=display ;;
    audio) expected=speaker ;;
  esac
  if ! load_platform "probe-$probe" \
      "$test_root/platforms/boards/probe-$probe.repl" "$expected"; then
    echo "SPIKE Prime platform probe failed: $probe" >&2
    probe_failed=1
  fi
done
test "$probe_failed" -eq 0

names_marker="$test_root/platform-names.ok"
load_platform full "$test_root/platforms/boards/spike-prime.repl" speaker \
  "python \"names = set(self.Machine.GetAllNames()); required = ['adc1', 'bluetoothButton', 'buttonLadders', 'centerButton', 'display', 'leftButton', 'rightButton', 'speaker', 'timer12']; assert all(any(name == item or name.endswith('.' + item) for name in names) for item in required); open('$names_marker', 'w').write('ok')\";" \
  | tee "$log"
test "$(cat "$names_marker")" = ok
for expected in adc1 display speaker timer12; do
  grep -Fq "$expected" "$log"
done
