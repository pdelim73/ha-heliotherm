# Technical design

Reference hardware: **Heliotherm HP08E-WEB**, controller software **2324**, read
through its `-X26 "Modem COM"` RS232 port via a Waveshare RS232-to-Ethernet
converter. Everything below that says "verified" was verified on that unit;
anything else is stated as an assumption or a limitation.

## 1. Transport: the native protocol over a transparent serial bridge

The integration opens a plain TCP connection to an RS232-to-Ethernet converter
running in **transparent TCP Server** mode. The converter copies bytes between
the socket and the pump's serial port without interpreting them, so the
integration speaks the controller's own framed ASCII protocol end to end.

Serial line (fixed on the converter, established empirically on SW 2324):
**19200 baud, 8N1, RTS/CTS hardware flow control**, full null-modem cable
(2↔3, 4↔6, 7↔8 crossed, 5↔5). 9600 baud does not work on this controller, and
without the RTS/CTS lines the pump never replies.

### Protocol summary

```
Request  (host → pump): 02 FD D0 E0 00 00 | LEN | ~CMD;       | CS
Response (pump → host): 02 FD E0 D0 xx 00 | LEN | ~REPLY;\r\n  | CS
```

- `LEN` counts the ASCII payload; in a response it includes the trailing `\r\n`.
- `CS` covers header + `LEN` + payload: for each byte `b`,
  `cs ^= b; cs ^= (b << 1) & 0xFF`.
- Header byte 5 of a response (`xx`) varies between frames.
- A session is `LIN` → reads → `LOUT`. The login command is `LIN`, not `LOGIN`.
- A read reply is a comma-separated field list. `VAL=` holds the value;
  `US=1` means the sensor/feature is fitted, `US=0` means it is not and `VAL` is
  a placeholder (e.g. `-50.0` for an absent temperature probe). Unknown
  registers return `~ERR,INVALID;` or a reply without `VAL=`.

### Alternatives considered and rejected

| Option | Why not |
|---|---|
| **Raspberry Pi + `socat` + HtREST + REST sensors** (this project's previous setup) | Needs a second always-on host and three moving parts (`socat` virtual serial port, the HtREST HTTP server, 61 hand-written YAML REST sensors). `socat` keeps the converter's single socket open permanently. Each REST sensor was its own HTTP request, and nothing was configurable from the UI. |
| **`htheatpump` library inside Home Assistant** | Works in principle (it is what HtREST uses, and `htha` in §5 takes this route), but adds an external dependency — `htha` installs `htheatpump` from a fork's git branch (`tcp-socket-and-tests`). This integration needs five commands; implementing them directly keeps the command surface small enough to audit as read-only (§2). |
| **Modbus TCP** (the `ha_heliotherm` family, `ha_heliotherm_2`) | Those integrations need Modbus enabled on the controller or a Modbus gateway (Heliotherm RCG, Brötje NEO-RKM). The `-X26` port on this unit was verified to speak the Heliotherm ASCII protocol; whether this 2005 controller supports Modbus at all was not tested. The converter's own Modbus gateway function is switched off; the bytes must pass through unchanged. |
| **RFC 2217** (serial-over-telnet with remote line control) | Not needed: the line settings never change and are fixed on the converter. Plain TCP is simpler. |
| **USB-serial adapter on the Home Assistant host** | Would work, but ties the Home Assistant machine to a cable run to the heat pump. The Ethernet converter lets them sit anywhere on the LAN. Not tested. |
| **One long-lived TCP session** | Rejected after a real failure: a session left idle between polls desynchronised, reads started mid-frame, and an earlier version blacklisted every parameter within a few cycles (flat-lined history). See §3.3. |

## 2. Coexistence: why this cannot change or disturb the heat pump

**No controller source is available.** The Heliotherm firmware is closed, so
nothing here can be proven from the controller's code. The guarantees therefore
come from this integration's own source, which you can check, and from what was
observed on the reference unit.

### 2.1 It only reads

Every byte the integration sends is built by `build_request()` in
[`protocol.py`](../custom_components/heliotherm/protocol.py), and the complete set
of commands it builds is:

| Command | Purpose | Built in |
|---|---|---|
| `LIN` | Log in (start of every poll) | `HeliothermClient.connect()` |
| `LOUT` | Log out (end of every poll) | `HeliothermClient.disconnect()` |
| `RID` | Read the serial number (setup) | `HeliothermClient.read_serial()` |
| `SP,NR=9` | Read the software version (setup) | `HeliothermClient.read_sw_version()` |
| `MP,NR=<n>` / `SP,NR=<n>` | Read one register | `HeliothermClient.read_param()` |

`<n>` comes only from the fixed parameter table in `const.py`. There are no
`number`, `select`, `switch`, `climate` or `button` platforms, and no services.

**This is enforced by the code itself.** `build_request()` checks every command
against a strict allowlist (`_ALLOWED_CMD_RE`: `LIN`, `LOUT`, `RID`,
`MP,NR=<digits>`, `SP,NR=<digits>`, full match only) and raises `ValueError`
before any byte is produced. Anything else is refused, including every request
that carries `VAL=`, a second command smuggled after a `;`, and other
controller commands such as `CLK`. Because `build_request()` is the only place
outgoing frames are made, a future code change would have to edit that one line
to send a write. Unit tests pin this down (§6).

### 2.2 It occupies the link only briefly

Each poll is one complete session: connect → `LIN` → reads → `LOUT` → close, with
the close in a `finally` block so the socket is released even after an error.
Between polls the integration holds no connection at all.

### 2.3 It does not share the link with other clients

The converter is configured for one connection and the pump handles one session,
so this integration **cannot coexist with another client of the same converter**,
and that is not attempted. In particular it is mutually exclusive with the
previous `socat` + HtREST setup: that setup's systemd unit runs
`socat PTY,… TCP:<converter IP address>:4196` with `Restart=always`, i.e. it holds
the converter's only socket permanently. Stop it before using this integration.

### 2.4 Effect of reads on the controller

Reading `MP`/`SP` registers is the same operation the HtREST setup performed
every minute for all 61 registers. No effect on the heat pump's operation has
been observed on the reference unit. Because the firmware is closed, this is an
observation, not a proof.

## 3. Architecture

```
custom_components/heliotherm/
├── __init__.py       entry setup/unload; reads serial + SW version; first refresh
├── protocol.py       asyncio TCP client, frame codec, checksum, error classes
├── coordinator.py    DataUpdateCoordinator: discovery pass, polling, blacklist
├── const.py          HtParam table: 26 MP + 35 SP registers with HA metadata
├── entity.py         shared base: device info, unique ID, availability
├── sensor.py         numeric registers  → sensor entities
├── binary_sensor.py  boolean registers → binary_sensor entities
├── config_flow.py    host/port setup (validated by reading RID) + options
├── strings.json, translations/en.json
└── manifest.json     local_polling, config_flow, no requirements
```

### 3.1 Poll cycle

One `DataUpdateCoordinator` serves every entity.

1. **Discovery (first poll after setup or reload).** Read all 61 registers once.
   A register joins the supported set only if it returns a real value (`VAL=`
   present and `US` not `0`). Entities are created afterwards, and only for the
   supported set. On the reference unit that is 22 of 26 `MP` and 29 of 35 `SP`
   registers.
2. **Every later poll** reads only the supported `MP` registers, plus the
   supported `SP` registers every `sp_interval` polls (default 10). Values from
   the last `SP` read stay in the dataset in between.
3. A 50 ms gap separates commands; the 2005 controller drops frames if pushed
   harder.

Rough cost at 19200 baud (arithmetic, not measured): a register reply is about
200 bytes, roughly 0.1 s of line time, so a measurement-only poll on the
reference unit (22 reads) takes a few seconds and discovery about ten.

### 3.2 Error handling

```
HeliothermError
├── HeliothermConnectionError   connection-level fault → abandon the whole poll
│   └── HeliothermFramingError  byte stream out of sync (bad response header)
└── HeliothermProtocolError     well-framed rejection of one register:
                                ERR reply, no VAL=, or US=0
```

- A `HeliothermProtocolError` (or an unparseable value) blacklists **that
  register only**: during discovery it is left out of the supported set; after
  discovery it is skipped until the next recheck.
- A `HeliothermConnectionError` aborts the poll, is reported to Home Assistant as
  `UpdateFailed`, and blacklists nothing. The next poll opens a fresh session.
- Every 30 polls the blacklist is cleared so an active register knocked out by a
  one-off fault is retried. Registers excluded at discovery are not in the poll
  groups, so they are never re-read.

### 3.3 Why the design looks like this

An earlier version kept one session open across the idle gap and treated a
malformed response header as "register unsupported". On this hardware an idle
session can desynchronise; the next read then started mid-frame, its "header"
was really the middle of a valid reply, and every following read in that cycle
was misaligned too. Within a few cycles all 61 registers were blacklisted, polls
did no I/O yet reported success, and history went flat. Decoding the logged
"garbage" headers showed they were real reply text read at the wrong offset.
The fix is the combination above: a fresh session per poll, and framing errors
classed as connection faults that never blacklist.

## 4. Entity reference

- **Unique ID**: `<serial>_<key>`. The serial comes from `RID`, so it is stable
  across IP changes.
- **Device**: name `Heliotherm <serial>`, model `HP08E-WEB` (fixed string),
  firmware from `SP,NR=9`, serial number from `RID`.
- **Source key**: the register the value is read from, e.g. `MP,NR=0`.
- **Scaling**: none. `VAL` is used exactly as the pump reports it, already in
  engineering units (°C with one decimal, bar, hours). Types are coerced as
  FLOAT → `float(VAL)`, INT → `int(float(VAL))`, BOOL → `bool(int(float(VAL)))`.
- **Null / absent handling**:
  - Register not supported at discovery (`US=0`, `ERR`, or no `VAL`) → **no
    entity is created**.
  - A whole poll fails → every entity is *unavailable* until the next successful
    poll.
  - A supported register is rejected mid-life → it keeps its last value until
    the 30-poll recheck retries it (see §7).
- **Pump range** is the `MIN … MAX` the pump itself reports for the register.
- **Reference unit** is the result of a live query of every register on the
  reference unit (HP08E-WEB, SW 2324).

| Entity | Register | Platform | Type | Unit | Device class | State class | Pump range | Reference unit |
|---|---|---|---|---|---|---|---|---|
| Temp. Aussen | `MP,NR=0` | sensor | FLOAT | °C | temperature | measurement | -20.0 … 30.0 | ✓ |
| Temp. Aussen verzoegert | `MP,NR=1` | sensor | FLOAT | °C | temperature | measurement | -20.0 … 30.0 | ✓ |
| Temp. Brauchwasser | `MP,NR=2` | sensor | FLOAT | °C | temperature | measurement | 0.0 … 60.0 | ✓ |
| Temp. Vorlauf | `MP,NR=3` | sensor | FLOAT | °C | temperature | measurement | 0.0 … 70.0 | ✓ |
| Temp. Ruecklauf | `MP,NR=4` | sensor | FLOAT | °C | temperature | measurement | 0.0 … 70.0 | ✓ |
| Temp. EQ_Eintritt | `MP,NR=6` | sensor | FLOAT | °C | temperature | measurement | -20.0 … 30.0 | US=0 → no entity |
| Temp. EQ_Austritt | `MP,NR=7` | sensor | FLOAT | °C | temperature | measurement | -20.0 … 30.0 | US=0 → no entity |
| Temp. Sauggas | `MP,NR=9` | sensor | FLOAT | °C | temperature | measurement | -20.0 … 30.0 | US=0 → no entity |
| Temp. Frischwasser_Istwert | `MP,NR=11` | sensor | FLOAT | °C | temperature | measurement | 0.0 … 70.0 | ✓ |
| Temp. Verdampfung | `MP,NR=12` | sensor | FLOAT | °C | temperature | measurement | -50.0 … 30.0 | ✓ |
| Temp. Kondensation | `MP,NR=13` | sensor | FLOAT | °C | temperature | measurement | -50.0 … 60.0 | ✓ |
| Temp. Heissgas | `MP,NR=15` | sensor | FLOAT | °C | temperature | measurement | 0.0 … 150.0 | ✓ |
| Niederdruck (bar) | `MP,NR=20` | sensor | FLOAT | bar | pressure | measurement | 0.0 … 10.0 | ✓ |
| Hochdruck (bar) | `MP,NR=21` | sensor | FLOAT | bar | pressure | measurement | 0.0 … 40.0 | ✓ |
| Heizkreispumpe | `MP,NR=22` | binary_sensor | BOOL | — | running | — | 0 … 1 | ✓ |
| EQ Pumpe (Ventilator) | `MP,NR=24` | binary_sensor | BOOL | — | running | — | 0 … 1 | US=0 → no entity |
| Warmwasservorrang | `MP,NR=25` | binary_sensor | BOOL | — | — | — | 0 … 1 | ✓ |
| Zirkulationspumpe WW | `MP,NR=29` | binary_sensor | BOOL | — | running | — | 0 … 1 | ✓ |
| Verdichter | `MP,NR=30` | binary_sensor | BOOL | — | running | — | 0 … 1 | ✓ |
| Stoerung | `MP,NR=31` | binary_sensor | BOOL | — | problem | — | 0 … 1 | ✓ |
| Hauptschalter | `MP,NR=36` | binary_sensor | BOOL | — | power | — | 0 … 1 | ✓ |
| FWS Stroemungsschalter | `MP,NR=38` | binary_sensor | BOOL | — | — | — | 0 … 1 | ✓ |
| Z Impulse Stromzaehl | `MP,NR=41` | sensor | INT | — | — | measurement | 0 … 1 | ✓ |
| Frischwasserpumpe | `MP,NR=50` | sensor | INT | — | — | measurement | 0 … 100 | ✓ |
| Verdichteranforderung | `MP,NR=56` | sensor | INT | — | — | measurement | 0 … 4 | ✓ |
| HKR_Sollwert | `MP,NR=57` | sensor | FLOAT | °C | temperature | measurement | 0.0 … 50.0 | ✓ |
| Liegenschaft | `SP,NR=3` | sensor | INT | — | — | measurement | 0 … 2147483647 | ✓ |
| WP_System | `SP,NR=4` | sensor | INT | — | — | measurement | 1 … 2 | US=0 → no entity |
| WW Type | `SP,NR=5` | sensor | INT | — | — | measurement | 0 … 3 | ✓ |
| FWS Type | `SP,NR=6` | binary_sensor | BOOL | — | — | — | 0 … 1 | ✓ |
| Puffer Type | `SP,NR=7` | binary_sensor | BOOL | — | — | — | 0 … 1 | ✓ |
| Verdichter_Status | `SP,NR=10` | sensor | INT | — | — | measurement | 0 … 7 | ✓ |
| Verdichter laeuft seit | `SP,NR=11` | sensor | INT | — | — | measurement | 10 … 100000 | ✓ |
| Verdichter Einschaltverz.(sec) | `SP,NR=12` | sensor | INT | s | duration | measurement | 0 … 10800 | ✓ |
| Betriebsart | `SP,NR=13` | sensor | INT | — | — | measurement | 0 … 7 | ✓ |
| HKR Soll_Raum | `SP,NR=69` | sensor | FLOAT | °C | temperature | measurement | 10 … 25 | ✓ |
| HKR Aufheiztemp. (K) | `SP,NR=71` | sensor | INT | — | — | measurement | 1 … 10 | ✓ |
| HKR Absenktemp. (K) | `SP,NR=72` | sensor | INT | — | — | measurement | -10 … -1 | ✓ |
| HKR Heizgrenze | `SP,NR=76` | sensor | INT | — | — | measurement | 10 … 23 | ✓ |
| HKR RLT Soll_oHG (Heizkurve) | `SP,NR=80` | sensor | FLOAT | °C | temperature | measurement | 15 … 30 | ✓ |
| HKR RLT Soll_0 (Heizkurve) | `SP,NR=81` | sensor | FLOAT | °C | temperature | measurement | 20 … 40 | ✓ |
| HKR RLT Soll_uHG (Heizkurve) | `SP,NR=82` | sensor | FLOAT | °C | temperature | measurement | 25 … 55 | ✓ |
| WW Normaltemp. | `SP,NR=83` | sensor | INT | — | — | measurement | 10 … 60 | ✓ |
| WW Hysterese Normaltemp. | `SP,NR=84` | sensor | INT | — | — | measurement | 1 … 10 | ✓ |
| WW Minimaltemp. | `SP,NR=85` | sensor | INT | — | — | measurement | 5 … 45 | ✓ |
| WW Hysterese Minimaltemp. | `SP,NR=86` | sensor | INT | — | — | measurement | 1 … 10 | ✓ |
| BSZ HKP Betriebsstunden | `SP,NR=153` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| BSZ HKP Schaltung | `SP,NR=155` | sensor | INT | — | — | total_increasing | 0 … 100000 | ✓ |
| BSZ EQ Betriebsstunden | `SP,NR=162` | sensor | INT | h | duration | total_increasing | 0 … 100000 | US=0 → no entity |
| BSZ EQ Schaltungen | `SP,NR=164` | sensor | INT | — | — | total_increasing | 0 … 100000 | US=0 → no entity |
| BSZ WWV Betriebsstunden | `SP,NR=165` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| BSZ WWV Schaltungen | `SP,NR=167` | sensor | INT | — | — | total_increasing | 0 … 100000 | ✓ |
| BSZ ZIPWW Betriebsstunden | `SP,NR=168` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| BSZ ZIPWW Schaltungen | `SP,NR=170` | sensor | INT | — | — | total_increasing | 0 … 100000 | ✓ |
| BSZ Verdichter Betriebsst. WW | `SP,NR=171` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| BSZ Verdichter Betriebsst. HKR | `SP,NR=172` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| BSZ Verdichter Betriebsst. ges | `SP,NR=173` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| BSZ Verdichter akt. Laufzeit | `SP,NR=174` | sensor | INT | h | duration | total_increasing | 0 … 100000 | ✓ |
| MKR2 Aktiviert | `SP,NR=222` | sensor | INT | — | — | measurement | — | no VAL → no entity |
| Energiezaehler | `SP,NR=263` | sensor | INT | — | — | measurement | — | no VAL → no entity |
| BSZ Verdichter Schaltung WW | `SP,NR=375` | sensor | INT | — | — | total_increasing | — | no VAL → no entity |

Names are the controller's own German parameter names. The `SP` registers hold
configuration values and operating counters. They are exposed as read-only
sensors.

The table was derived from the `htheatpump` parameter database. On the reference
unit, every register's own `NAME=` reply agrees with that database (allowing for
the pump's 20-character truncation) except `MP,NR=41`: the database calls it
*BSZ Verdichter Schaltungen* (range 0 … 100000), but this pump reports
*Z Impulse Stromzaehl* (range 0 … 1). Since 1.4.0 the entity uses the pump's
name (see §7).

## 5. Comparison with other Heliotherm integrations studied

Studied on 2026-09-28 from each project's README, manifest and repository
layout. Nothing below was run by this project except the previous HtREST setup.

| | This integration | [`silviuk/htha`](https://github.com/silviuk/htha) | [`mbuchber/ha_heliotherm`](https://github.com/mbuchber/ha_heliotherm) (+ forks) | [`gamgamstylep/ha_heliotherm_2`](https://github.com/gamgamstylep/ha_heliotherm_2) | Previous setup: HtREST + REST sensors |
|---|---|---|---|---|---|
| Transport | TCP to a transparent RS232 bridge on `-X26` | Serial-over-TCP (README example: ser2net, 9600 8N1) | Modbus TCP | Modbus TCP or Modbus RTU (RS485) | `socat` virtual serial port → [HtREST](https://github.com/dstrigl/HtREST) HTTP API |
| Controller side | Heliotherm ASCII protocol | Heliotherm ASCII protocol via `htheatpump` | Modbus enabled on the controller, Heliotherm RCG or Brötje NEO-RKM | Same as `ha_heliotherm` | Heliotherm ASCII protocol via `htheatpump` |
| Python requirements | none | `htheatpump` from a fork's git branch | `pymodbus` | `pymodbus>=3.0.0` | separate host running HtREST |
| Writes to the pump | **never** | yes (setpoints, operating mode); writes disabled by default, enabled with a "Write Protection" switch | yes (operating mode, room and hot-water temperatures) | yes, with an optional read-only mode | no (only GET requests were configured) |
| Tested hardware (per README) | HP08E-WEB, SW 2324 | HP07S08W-S-WEB | — | — | HP08E-WEB, SW 2324 |
| Setup | UI config flow | UI config flow | UI config flow | UI config flow | 61 YAML REST sensors |

`hstrohmaier/ha_heliotherm`, `EricSand/ha_heliotherm` and
`deggle/ha_heliotherm_en` (English names) are GitHub forks of
`mbuchber/ha_heliotherm`. "—" means not recorded in this study.

Where this integration fits: you want to use the pump's `-X26` serial port, with
no extra host or dependency, and the heat pump must not be controllable from
Home Assistant.

## 6. Verification performed

On the reference unit (HP08E-WEB, SW 2324):

- **Frame codec**: the `LIN` and `RID` request frames built by the code are
  byte-identical to frames captured from a working session
  (`02 FD D0 E0 00 00 05 7E 4C 49 4E 3B 4C` and `… 7E 52 49 44 3B 70`), and the
  checksum function reproduces the pump's own checksum byte on a captured reply.
- **Register sweep**: every register in the table was queried live; the results
  are the *Reference unit* column in §4 (51 real values, 7 `US=0`, 3 without
  `VAL`).
- **Home Assistant**: an earlier build of this integration, before discovery
  filtering was added, ran on the reference installation and showed live values
  for the supported registers on the device page.
- **Desync diagnosis**: the flat-line failure in §3.3 was diagnosed from real
  debug logs, whose garbled headers decoded back to real reply text.

Not yet verified on the reference unit, covered by unit tests only: discovery
filtering (unsupported registers get no entity) and the command allowlist.

Unit tests (`pytest`, 59 tests, run locally; they stub Home Assistant so they run
without it):

- checksum and full frames against the captured reference frames;
- read-only allowlist: every register in the table is accepted; writes
  (`SP,NR=83,VAL=50`), smuggled commands, unused controller commands and
  malformed input are refused, and a refused command writes nothing to the
  socket;
- value coercion for FLOAT/INT/BOOL; missing `VAL` and `US=0` raise
  `HeliothermProtocolError`; a `STATUS=0` field is not mistaken for `US=0`;
- a bad response header raises `HeliothermFramingError`; a clean `ERR` reply
  raises `HeliothermProtocolError`;
- the desync regression: a framing error aborts the poll and blacklists nothing;
- discovery: unsupported registers are absent from the data and from the poll
  groups, and are never re-read, including across a recheck boundary;
- parameter table integrity: no duplicate keys or registers, valid types.

```bash
pip install -r tests/requirements.txt
python -m pytest
```

Continuous integration: every push to `main`, every pull request and a weekly
schedule run Home Assistant's `hassfest` validator on the integration
([workflow](../.github/workflows/validate.yml)); results are in the repository's
*Actions* tab. The unit tests are not part of CI.

## 7. Known limitations

- **One unit tested.** Only an HP08E-WEB with SW 2324. Other Heliotherm
  controllers using the same protocol may work, but may need different serial
  settings. Untested.
- **One client at a time.** The converter socket is exclusive (§2.3).
- **One register per round trip.** The protocol has no bulk read. At 19200 baud,
  polling faster than about every 30–60 s gains little.
- **Supported set is fixed at setup.** If hardware is added or the firmware
  changes, reload the integration to re-run discovery.
- **Stale value after a mid-life rejection.** If a supported register starts
  returning `ERR` or `US=0`, its entity keeps showing the last value (not
  *unavailable*) until the 30-poll recheck retries it.
- **`MP,NR=41` meaning unknown.** Named after the pump's own reply,
  *Z Impulse Stromzaehl*, which is 20 characters and so probably truncated. The
  pump reports a range of 0 … 1; what the value means is not documented. It is
  recorded as a plain `measurement`. Before 1.4.0 it was mislabelled *BSZ
  Verdichter Schaltungen* (`total_increasing`), the name the `htheatpump`
  database gives register 41.
- **Raw codes.** *Betriebsart*, *Verdichter_Status*, *Verdichteranforderung* and
  similar registers are shown as raw integers. Their meaning on SW 2324 is not
  mapped.
- **Unconfirmed units.** Some registers have no unit (e.g. *Frischwasserpumpe*,
  range 0 … 100, *Verdichter laeuft seit*). *BSZ Verdichter akt. Laufzeit* is
  declared in hours, which was not confirmed.
- **Names are German** controller names; there are no entity-name translations.
- **No brand icon** in Home Assistant.
- **Minimum Home Assistant 2024.12.0.** The options flow uses the `config_entry`
  property that `OptionsFlow` provides itself. The Home Assistant developer blog
  announced it on 2024-11-12, after 2024.11 had shipped, so 2024.12 is the first
  release with it. Only tested on the reference installation's current release.
