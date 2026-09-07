# Completed simulation checkpoints

## 2026-09-07 — SPIKE Essential LED path (R6.3)

Added an MIT-licensed LP50xx register/color model and wired the Essential
STM32F413 FMPI2C1 instance at `0x40006000`, IRQs 95/96, DMA1 streams 0/1, and
active-high PB13 enable/reset. Focused tests cover the exact firmware-shaped
initialization write, DMA request enables, fixed and auto-increment access,
software/hardware reset, global output disable, raw output state, and defensive
rendered RGB-module snapshots. Analogue current, emitted-light physics and PWM
phase remain outside the model.
