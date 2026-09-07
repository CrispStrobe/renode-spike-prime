# SPIKE brick-device models

This fork branch adds MIT-licensed, deterministic SPIKE Prime and Essential
brick-level observation models. Use the optional platform overlays in
`platforms/boards/` and the monitor-visible state described in
`docs/platforms/spike-brick-devices.md`.

Today this covers Essential's center button and basic power/charger policy,
Prime's raw TLC5955 display snapshot and speaker byte sink, and richer IMU FIFO
and interrupt behavior. It is suitable for source-only CI and controlled
firmware experiments, not as evidence that every physical or timing behavior of
a LEGO hub is reproduced. In particular, Prime ADC buttons, analog audio,
charger electronics, IMU physics, and decoded optical output remain outside the
current model.

