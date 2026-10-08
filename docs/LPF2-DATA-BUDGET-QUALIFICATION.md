<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# LPF2 DATA budget Runtime candidate

This branch pins Infrastructure candidate
`4f705f40b93f7293cdc0edac6eb253540e967ff9` to compile and qualify its
[bounded device DATA report control](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/4f705f40b93f7293cdc0edac6eb253540e967ff9/docs/LPF2-DATA-REPORT-BUDGET.md).
Compiled Runtime/model execution is pending. Neither firmware nor desktop
consumer pins are changed by this candidate.

The prior Runtime pin is `adf40d98062a6b31aae7ef86e1ae5f289eebdc48`.
Infrastructure main base `87766f795473691fad1640cd8fc200017cc0c294` has the
same tree as that pin; the candidate adds only the DATA budget implementation,
its tests/mutation tool and documentation. This qualification does not import
an unrelated model change under the budget's name.

The existing model workflow builds native translators and source-only headless
Renode, runs focused and complete managed peripheral suites, and retains its
board/CPU/console checks. It adds the thirteen DATA-budget cases to the focused
filter, then recompiles three actual mutations after existing checks. The
mutation tool requires NUnit assertion failures, restores exact source bytes
and rebuilds/retests the baseline. No new firmware, model binary, original image,
raw transcript or private input is uploaded.

The adapter retains MIT attribution and grants; new fixture/control/docs use
BSD-3-Clause. Existing dependency source and licence obligations remain applicable.
This is not a full source-to-binary or licence-clearance claim.

Before merge/adoption, record exact Runtime/Infrastructure heads and all enabled
CI conclusions. Run the affected actual own-firmware native/Python and Classic
motor regressions with this pair, preserving previous consumed pins and failures.
The new active-session experiment must then use real guest syscalls and a bounded
external UART frame budget; it must not alter engine queues or session counters.
Model-only controls do not establish invalid-call non-consumption, guest reset
behavior, atomic motor authority or physical-device fidelity.
