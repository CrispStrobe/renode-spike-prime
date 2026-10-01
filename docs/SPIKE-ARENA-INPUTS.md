# Synthetic arena input contract

The `arena.inputs` command contains exactly `sensors` and `loads` arrays, each
at most six entries, with unique ports A–F across both arrays. Sensors contain
`port`, `kind`, `values`. Distance values contain integer `distanceMillimeters`
(-1 unknown, otherwise 0–65535). Color contains integer `colorId` (0–255),
`reflectionPercent`, `ambientPercent` (0–100). Force contains integer
`forcePercent` (0–100) and boolean `pressed`. Loads contain `port` and integer
`percent` (0–100). Unknown fields, duplicate ports and booleans used as numbers
are rejected before changing devices. Caller input never names model paths,
monitor commands, memory addresses, firmware or network endpoints.

Own NuttX LPF2 models accept these inputs through their public setters when
identity is `brickwright-nuttx`, transport `none`. That alone does not prove
firmware drivers consume these model inputs.

The separate `brickwright-arena-demo` simulation-only Cortex-M4 guest consumes
fixed mailbox inputs and computes actual guest motor outputs. Its source and
ABI are in `CrispStrobe/brickwright-spike-prime-fw/simulation/arena-demo` under
BSD-3-Clause. A/B are motors, C color, D distance, E force. It advertises
`arena-inputs/v1`, `arena-clock/v1`, `guest-motor-output/v1` and
`state-sample/v1`; only this complete
contract is suitable for the current desktop arena adapter. Its clock is the
guest millisecond counter, not monitor host time. `state.sample` accepts no
arguments and requests a fresh bounded snapshot without advancing guest time.
Clients retain their prior snapshot behavior for older services that do not
advertise this capability. It is a bounded demonstration,
not full SPIKE firmware, physical calibration or an arbitrary program runner.

Build the guest locally, then stage a new package directory:

```
python3 tools/stage_spike_arena_demo.py --firmware /tmp/brickwright-arena-demo/arena-demo.elf --executable /absolute/renode --output /tmp/brickwright-arena-package
```

`pins.json` supplies compile-time `BW_RENODE_*` environment values for the
Brickwright desktop build. Review the package manifest and keep the complete
package immutable. The manifest includes imported helper files and the platform;
these must be packaged with the pinned state script. Never copy generated
packages or execution receipts into this public checkout.

Reproduce source validation:

```
python3 -m unittest discover -s tests/tools -p 'spike_arena*test.py' -v
python3 -m unittest discover -s tests/tools -p 'spike*test.py' -v
```

New input validators, mailbox adapter, staging tool and their tests are
BSD-3-Clause (Brickwright contributors, 2026); existing service components
retain their original licensing. Full license: `licenses/arena-BSD-3-Clause.txt`.
