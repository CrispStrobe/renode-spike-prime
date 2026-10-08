<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# LPF2 DATA budget Runtime candidate

This branch pins Infrastructure candidate
`1253d925accca23dfda66d5bca61e78498dcb64f` to compile and qualify its
[bounded device DATA report control](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/1253d925accca23dfda66d5bca61e78498dcb64f/docs/LPF2-DATA-REPORT-BUDGET.md).
Compiled Runtime/model execution is pending. Neither firmware nor desktop
consumer pins are changed by this candidate.

The prior Runtime pin is `adf40d98062a6b31aae7ef86e1ae5f289eebdc48`.
Infrastructure main base `87766f795473691fad1640cd8fc200017cc0c294` has the
same tree as that pin; the candidate adds only the DATA budget implementation,
its tests/mutation tool and documentation. This qualification does not import
an unrelated model change under the budget's name.

The existing model workflow builds native translators and source-only headless
Renode, runs focused and complete managed peripheral suites, and retains its
board/CPU/console checks. It adds the eighteen DATA-budget cases to the focused
filter, then recompiles three actual mutations after existing checks. The
mutation tool requires NUnit assertion failures, restores exact source bytes
and rebuilds/retests the baseline. Twelve host controls exercise the runner failure paths: eight use mocked compiler
results and four check the small Python process supervisor. Two supervisor
mutations fail live-descendant assertions. They do not execute C# or Renode.
The supervisor cleans up its owned process group on return, timeout and caught
Python exceptions; mutation builds disable shared compilation and node reuse. Raw mutation results stay
in the runner temporary directory and may disappear when the runner is cleaned;
test identities and hashes remain in the workflow log. No new firmware, model binary, original image,
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
