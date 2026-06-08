# Felicity Battery — Home Assistant

Monitor Felicity Solar batteries (e.g. FLA24100) via the FSolar cloud API.

## Install (HACS)

1. Add this repository as a custom repository (type: **Integration**).
2. Install **Felicity Battery** and restart Home Assistant.
3. Add the integration and sign in with your FSolar **email and password**.

## Sensors

State of charge / health, voltage, current, power, capacity, temperature,
per-cell voltages & temperatures, charge/discharge limits, and charging status.

> Cloud polling via `shine-api.felicitysolar.com`. Default update interval: 60s.
