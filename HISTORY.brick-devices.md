# Brick-device checkpoint history

## 2026-09-07 — deterministic board observations

- Infrastructure `e3bbdaad0` added MIT-only power policy, PCM sink, and richer
  LSM6DS3TR-C models with focused NUnit coverage.
- Source-only board overlays wire evidenced Prime and Essential pins without
  bundling firmware or vendor controller data.
- The focused baseline passed 11 NUnit tests before amplifier semantics were
  tightened; the final test result is recorded in the corresponding commit.

