# Upstream review manifest

This manifest is the replay contract for generic changes. It contains no LEGO,
TI, firmware-image, or Brickwright interface dependency.

## Baselines

- Renode: `ab721d88e135a1bcb8ed2ecc5a38f51cbe61fdd2`
- Renode Infrastructure: `066a7f13c052215632d469c995c89aea37c573b1`

The product branch is 40 Renode commits and 18 Infrastructure commits ahead of
its merge bases, while current upstream is respectively 1002 and 811 commits
ahead. Replaying isolated patches is safer and more reviewable than rewriting
the product branch.

## Replay branches

`feat/upstream-generic-stm32-review` contains one cleanly replayed patch:

1. `0de918d1e`: correct STM32 DMA completion, with focused regression tests.

`feat/upstream-generic-devices-review` contains four ordered patches:

1. `e9325a85a`: TLC5955 shift/latch model and tests.
2. `c7451e26d`: LSM6DS3TR-C register model and tests.
3. `e882245d4`: generic NOR/W25Q256 behavior and tests. The replay preserves
   upstream's status-register-stub option and adds the optional secondary
   status opcode after it.
4. `0c8851bbb`: LP50xx LED model and tests, split from the original mixed
   LP50xx/STM32-I2C commit.

The SDK-style test project discovers test files automatically, so obsolete
explicit `Compile` entries were discarded during replay.

## Required before upstream submission

- Port the UART idle/enable patch onto upstream's managed receiver thread.
- Rework the SPI/UART paced DMA request series against current peripheral APIs.
- Split and port the STM32F7 I2C DMA portion independently from LP50xx.
- Build each topic in a current, fully initialized Renode checkout and run only
  its named fixture first, then the complete peripheral suite.
- Review commit messages and authorship, then submit one topic at a time. Do not
  open upstream pull requests from automation.

The replay worktrees passed `git diff --check`. A fully initialized current
Renode superproject generated its build targets and compiled native x86 and ARM
cores plus several managed dependencies. Its focused .NET 8 test build did not
reach the test runner before the bounded audit ended, so this is not a native
pass and the native gate remains pending.
