# Protected guest workload and cold storage recovery

`tools/check_prime_nuttx.py` executes source-built protected NuttX kernel and
userspace images. Requests use the ELF-resolved program mailbox. The fixture
does not replace guest instructions, completion state or encoder feedback.
Generated images, media, transcripts and resource samples stay in a new private
output directory. Existing evidence is never overwritten.

## Workload

Select `--workload-test` after building the TI-free `simulation` profile. The
ordinary robot regression runs first. Thirty additional cycles alternate signed
A/B motion while a force-sensor wait remains active. Each cycle checks actual
model displacement and powered motion, rejects SAVE/LOAD while running, and
either completes through the external force input or cancels. Old program IDs
cannot stop a successor. Terminal programs release power, then SAVE/LOAD must
restore the same program in READY.

The host observes emulator-process RSS once per second, with a 1536 MiB ceiling
and the existing independent wall-time limit. Growth is measured from the first
sample after both ten workload cycles and fifteen wall seconds, with the same
64 MiB bound as R04. It requires at least two post-warmup samples. This is sampled
process RSS, not a continuous peak, proportional memory or guest heap accounting.
It does not independently qualify socket recovery under this workload.

## Cold storage

Select `--storage-test` for six separate emulator processes:

1. SAVE maximum-size native and completed Python programs to synthetic NOR.
2. Restore exact native flash bytes, LOAD and execute the native program.
3. Restore exact Python flash bytes, LOAD and execute the Python program.
4. Restore native media with one payload bit changed. Require `EBADMSG`, preserve
   a distinct live program and every byte of the medium, then execute that live
   program successfully.
5. Restore native media, replace the program and inject one actual modeled NOR
   program-operation failure. Require successful acknowledged SAVE and evidence
   that the requested failure occurred.
6. Restore the resulting media in another process. The acknowledged replacement
   must LOAD and execute successfully.

The damage helper requires exactly one complete expected native header and
changes only its first payload byte. It retains both source and damaged hashes.
The NOR injection uses the compiled model's public fault counters; it does not
patch a filesystem return value. This is one failed-program replacement case,
not exhaustive interruption coverage or physical brownout evidence. Calibration
and Bluetooth key persistence need their own guest tests.

## Source and evidence boundaries

Every invocation records kernel, userspace, executable and qualification-source
SHA-256s, per-phase wall time, return status and RSS samples, including failures.
`--compiled-runtime` stages only offline board data; callers must retain the
compiled Runtime's full build identity. The default source-extension route stays
separately labeled. An entrypoint hash alone does not identify its shared
libraries or establish an installed consumer's runtime closure.

On 2026-10-28, firmware source `91cf0c07784441ac114b85a1705737327db2d9f8`
passed the ordinary robot, six-motor, thirty-cycle workload and all six storage
phases on macOS with stock Renode 1.16.1 and source-staged Infrastructure
`bb2c96fd2656f686d4b06683df4ece234f33b206`. The workload had 133 observations,
21,312 KiB observed RSS growth and a 492,944 KiB sampled peak. The six-motor
regression retained its three-degree position tolerance and had 146 observations.
These results do not qualify the new compiled Linux Runtime, an installed GUI,
concurrent Bluetooth traffic or physical hardware.

The initial workload completed all thirty cycles but failed an incorrect
max-minus-min RSS comparison. Host memory reclamation lowered that minimum;
the test counted a decrease as growth. Its original receipt is retained. The
corrected comparison uses R04's fixed post-warmup baseline and preserves the
64 MiB threshold; a fresh complete invocation passed. Controls reject growth one
KiB beyond the bound and ensure reclamation never lowers the baseline.
