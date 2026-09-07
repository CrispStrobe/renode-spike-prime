# Brick-device checkpoint history

## 2026-09-07 — deterministic board observations

- Infrastructure commits `e3bbdaad0` and `1c4e78466` added MIT-only power
  policy, bounded PCM sink, and richer LSM6DS3TR-C models. Merge
  `f5122307d` combines them with the accepted LPF2 model line.
- Source-only board overlays wire evidenced Prime and Essential pins without
  bundling firmware or vendor controller data.
- The final focused power/audio/IMU suite passed 12 NUnit tests on .NET 8
  Release. The source-only platform wiring check also passed.
