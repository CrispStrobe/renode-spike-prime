<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# LPF2 DATA budget Runtime candidate

This branch pins Infrastructure candidate
`1253d925accca23dfda66d5bca61e78498dcb64f` to compile and qualify its
[bounded device DATA report control](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/1253d925accca23dfda66d5bca61e78498dcb64f/docs/LPF2-DATA-REPORT-BUDGET.md).
Actual compiled Runtime/model qualification passed at source
`8f7696aac606d8de90c1a6a0930e48655f03530a`; the affected NuttX guest matrix
also passed. Separate upstream-MicroPython guest qualification remains pending.
This Runtime candidate does not change installed desktop consumer pins.

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
and rebuilds/retests the baseline. At the model-tested Infrastructure pin, twelve host controls exercise the runner
failure paths: eight use mocked compiler results and four check the small Python
process supervisor. The subsequent host-test-only correction at
`fe7841c8d547f2aba550eaceace1d61d3abfc63c` handles a disappearing Linux process
entry and adds a thirteenth control. Both attribution checks passed there; model,
C# fixture and mutation-runner bytes remain those tested at `1253d925`. Two supervisor
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

## Support-profile integration failure and correction

[The first paired run](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37761874920)
at Runtime `79429555b420a63e9ce94ee0ad0828755462225b` stopped in the source-only
support-profile gate before native/C# compilation. The offline MicroPython
profile still required Infrastructure `adf40d98062a6b31aae7ef86e1ae5f289eebdc48`,
so its exact-byte verifier correctly rejected the new `LegoLpf2Port.cs`.
No C# tests or mutation checks ran; this was not a model assertion failure.

This candidate now explicitly advances the offline support-profile source pin
and its immutable workflow fetch to `1253d925accca23dfda66d5bca61e78498dcb64f`.
Exact consumed-source verification remains enabled; no source substitution or
permissive fallback is added. Firmware and installed desktop consumer pins stay
unchanged. The independently supplied upstream-MicroPython application profile
also needs actual guest qualification with this candidate before adoption; source
packaging controls and model tests alone do not qualify that application route.

## Actual compiled and own-firmware results

[Runtime run 37764701627](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37764701627)
passed at source `8f7696aac606d8de90c1a6a0930e48655f03530a` and Infrastructure
`1253d925accca23dfda66d5bca61e78498dcb64f`. All eighteen DATA-budget cases passed.
The three rebuilt model mutations produced fifteen, eleven and one assertion
failures respectively; all eighteen cases passed again after exact source
restoration and rebuilding. The full peripheral suite passed 584 cases with five
skipped. Focused, console, retained native topology and target checks also passed.
Do not count skipped cases as executed or claim every raw TRX file is archived.

[Firmware run 37775158539](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37775158539)
passed both profiles at source `3238f2ba9d0e2f5574ad86c1a4672693353a358b` with
this exact Runtime/model pair. It exercised protected boot, actual protected
syscall refusals, retained program restarts, storage, the HCI bridge and seven
Bluetooth-air scenarios. The
[firmware qualification record](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/bb5b625b928c4100f1ddc75a55ac21f1d0c9cd9e/docs/project/lpf2-budget-pair-qualification.md)
records its observed boundary and userspace resource measurements. The refusal
probe runs only in ordinary simulation. Active-session DATA polls and atomic PWM
admission remain separate experiments.

This later documentation head changes no executable source, model pin or workflow.
The separately supplied MicroPython application still needs qualification through
both compiled models and the verified offline source profile before adoption.
