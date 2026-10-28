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
passed the robot baseline, six-motor regression, thirty-cycle motor/sensor/storage
workload and all six cold-storage phases on independently compiled Linux and
macOS Runtime builds. Both bind Infrastructure
`bb2c96fd2656f686d4b06683df4ece234f33b206` and support resources
`9d7824771f3db67663950cae06f5bb7f89fbf33b`.
The [receipt](receipts/2026-10-28-nuttx-guest-qualification.json) binds images,
qualification sources, private build inventories and original phase receipts.

| Compiled host | Workload observations | Sampled peak RSS | Post-warmup RSS growth |
| --- | ---: | ---: | ---: |
| Linux | 275 | 360,268 KiB | 1,056 KiB |
| macOS | 275 | 373,504 KiB | 2,928 KiB |

Six-motor position tolerance remains three degrees. Every cold-storage phase
passed independently on both compiled hosts. These results do not establish
installed GUI acceptance, concurrent Bluetooth traffic or physical durability.

Preserved failures explain the final fixture. The first Linux workload exposed
a previously queued pressed force sample; a guest release-wait now precedes
motor power. Its successor exposed asynchronous braking/encoder completion;
the fixture now observes actual terminal state within the unchanged one-guest-
second bound. Neither repair substitutes completion or sensor data.

The first macOS source-extension run used an incorrect max-minus-min RSS
comparison. The corrected comparison uses R04's fixed post-warmup baseline and
keeps the 64 MiB threshold; controls reject one KiB beyond it and ensure
reclamation never lowers that baseline. Later stock-Runtime/source-extension
runs completed the functional workload, but one still exceeded the unchanged
RSS-growth guard. That original failure remains retained and the legacy route
has no resource qualification claim. The separately built current compiled
macOS Runtime passed the same final fixture and unchanged resource guards;
it is the compiled result reported above.
