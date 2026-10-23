# Coherent program observations at a paused lockstep boundary

The full-firmware mailbox publishes status and Python output with sequence
locks. An exact clock quantum can pause the CPU while a sequence is odd.
That is an unavailable observation, not a valid partial frame or permission
to advance the CPU beyond the requested quantum.

The `nuttx-program-publication/v1` capability describes these additive fields:

- `lifecycle.nuttxProgram.publicationSeq`: the nonzero even uint32 sequence
  checked around the returned status bytes.
- `lifecycle.nuttxProgramReplySeq`: the real even request/reply sequence checked
  around the accompanying `nuttxProgramReply` packet. It is absent with the reply.

Only lockstep command snapshots and the following snapshot of an accepted
deferred START/STOP in active lockstep permit a typed unavailable status,
output or storage observation to be absent. They never reuse prior bytes or
advance time to complete a publication. Ordinary blocking packet/upload sampling
remains strict. Invalid headers, addresses, packet fields, lengths and bounds
remain errors. Capability admission describes supported functionality separately
from a particular observation's availability. Existing ordinary addressed-sensor
readiness admission remains unchanged; the lockstep admission additionally
recognizes a validated nonzero in-progress publication.

Status, output, reply and storage are observed independently. A reply is emitted
only when request and reply sequences are equal and unchanged around its bytes;
otherwise the worker may be replacing the previous reply. Completed storage
metadata requires its actual matching reply. Flash-checkpoint metadata requires
its corresponding storage observation; unavailable coupled payloads remain absent.

A new START acknowledgement can precede refresh of the prior COMPLETE status.
Consumers must validate the real pending reply sequence/opcode/program id and
keep acknowledgement handling separate from status freshness. Successful ACK
state describes that acknowledged control. Queued Stop must remain responsive.
A status from the ACK frame cannot overwrite that state as a newer observation;
subsequent status must advance beyond the publication version observed with the
ACK. If the version was unavailable, first establish a coherent floor and then
require an advance. Output freshness is independent. A retained old output cannot
satisfy a new execution's markers. Finite consumers may explicitly refuse sequence
reset/wrap and require a new session; they must not alias reset as advancement.

Pure source/protocol controls are not guest qualification. Actual own-firmware
qualification must retain the existing clock quanta, motion thresholds, virtual
and wall bounds, malformed-data cuts and all named Python cases. Persistent
unavailability must fail those same bounds. No hardware accuracy is established.
