# Heliotherm Heat Pump (Read-Only) for Home Assistant

A Home Assistant custom integration that reads a Heliotherm heat pump's
measurements, settings and operating counters directly over its serial
`-X26 "Modem COM"` port, bridged to the LAN by a transparent RS232-to-Ethernet
converter. It speaks the controller's own protocol natively — no extra host, no
`socat`, no HtREST, no Python dependencies.

It is **read-only**: it never sends a command that could change a setting on the
heat pump.

> Unofficial project, not affiliated with or supported by Heliotherm. Developed
> and tested against one HP08E-WEB with controller software 2324.

## Documentation

- [Installation guide](docs/installation.md) — prerequisites, HACS custom
  repository, setup, options, troubleshooting, updating, uninstalling.
- [Technical design](docs/technical-design.md) — transport choice, why it cannot
  change the heat pump, architecture, full entity reference, comparison with
  other Heliotherm integrations, verification, known limitations.

## At a glance

| | |
|---|---|
| Tested hardware | Heliotherm HP08E-WEB, controller software 2324 |
| Pump interface | `-X26 "Modem COM"` RS232, 19200 baud 8N1, RTS/CTS |
| Network bridge | Any transparent RS232-to-Ethernet converter in TCP Server mode (tested: Waveshare) |
| Protocol | Heliotherm framed ASCII protocol, implemented natively in `asyncio` |
| Access | Read-only — no write command exists in the code |
| Entities | Up to 61 (26 measurements + 35 settings/counters); only registers the pump actually supports are created — 51 on the reference unit |
| Polling | Measurements every 60 s (configurable 30–600 s); settings/counters every 10th poll |
| Setup | UI config flow (host + port) |
| Dependencies | None beyond Home Assistant |
| Minimum Home Assistant | 2024.12.0 |
| Installation | HACS → custom repository |

## License

[MIT](LICENSE)
