# Installation guide

Target: any Home Assistant installation with [HACS](https://hacs.xyz) (e.g.
Home Assistant OS on a Raspberry Pi). If you don't have HACS yet, install it
first — see [hacs.xyz](https://hacs.xyz).

## 0. Prerequisites

### Hardware chain

```
Heat pump -X26 "Modem COM" (RS232)
  → null-modem cable
  → transparent RS232-to-Ethernet converter (TCP Server mode)
  → your LAN
  → Home Assistant
```

The null-modem cable **must** cross the handshake lines as well as the data
lines. A 3-wire cable (pins 2/3/5 only) connects at TCP level but the pump never
answers.

| Converter DB9 | Pump -X26 DB9 | Signal |
|---|---|---|
| 2 | 3 | RX ↔ TX |
| 3 | 2 | TX ↔ RX |
| 4 | 6 | DTR ↔ DSR |
| 5 | 5 | GND |
| 6 | 4 | DSR ↔ DTR |
| 7 | 8 | RTS ↔ CTS |
| 8 | 7 | CTS ↔ RTS |

### Converter settings

| Setting | Value |
|---|---|
| Baud rate | **19200** (9600 does not work on controller software 2324) |
| Data bits / parity / stop bits | 8 / none / 1 |
| Flow control | **RTS/CTS** |
| Work mode | **TCP Server**, transparent (no protocol conversion) |
| Local port | **4196** (any port works; you enter it during setup) |
| Max. connections | 1 |
| RFC2217 / Modbus | off |

Give the converter a fixed IP address (a DHCP reservation on your router) so it
doesn't move.

### One client at a time

The converter and the pump each handle a single session. **Stop anything else
that connects to the converter** — for example an older `socat` + HtREST bridge,
which keeps a permanent connection — before adding this integration. Running two
clients at once is not supported and was not tested.

## 1. Add the repository to HACS

1. In Home Assistant, open **HACS** in the sidebar.
2. Click the **⋮** menu in the top right → **Custom repositories**.
3. Repository: `https://github.com/pdelim73/ha-heliotherm`
4. Type: **Integration**.
5. Click **Add**.

## 2. Download

1. Search HACS for **Heliotherm Heat Pump (Read-Only)** and open it.
2. Click **Download** and confirm.

### Coming from a manually copied install

If you previously copied the files into `config/custom_components/heliotherm/`
yourself, delete that folder (Samba share, SSH or the File editor add-on)
**before** downloading via HACS. A download doesn't delete files that no longer
exist in the repository, and older builds left extra files behind. Your existing
configuration entry, entities and history are stored by Home Assistant, not in
that folder, so they carry over unchanged.

## 3. Restart Home Assistant

**Settings → System → Restart.** A newly downloaded integration is only picked
up after a full restart.

## 4. Add the integration

1. **Settings → Devices & Services → Add Integration**.
2. Search for **Heliotherm Heat Pump (Read-Only)**.
3. Enter:
   - **Host**: `<converter IP address>`
   - **Port**: `4196` (or whatever you set on the converter)
4. Submit. The integration connects, logs in and reads the pump's serial number
   to confirm the link. The serial becomes the device's identity, so the same
   pump can't be added twice.

On success you get one device, **Heliotherm &lt;serial number&gt;**, with its
firmware version on the device page. During the first poll the integration asks
the pump for every register it knows (61) and creates entities **only for those
that return real data**. Sensors this unit doesn't have (for example
ground-source/EQ sensors that aren't fitted, or counters this firmware doesn't
implement) are not created at all.

There are no controls: this integration never writes to the pump.

## 5. Options

**Settings → Devices & Services → Heliotherm Heat Pump (Read-Only) → Configure**

| Option | Default | Range | Meaning |
|---|---|---|---|
| Polling interval | 60 s | 30–600 s | How often live measurements are read |
| Read settings every N cycles | 10 | 1–100 | Settings and counters change rarely; 10 means every ~10 minutes at the default interval |

Saving the options reloads the integration, which also re-runs the
supported-register discovery.

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Cannot reach the converter" during setup | Wrong IP/port, converter offline, or another client using the converter | Check IP and port, power, network; stop any other client of the converter |
| "Connected, but the heat pump did not respond correctly" | Wrong serial settings or a 3-wire cable | 19200 8N1 **RTS/CTS**, transparent TCP Server; full null-modem cable (see §0) |
| All entities go unavailable | A poll cycle failed (converter unreachable, or another client using it) | Entities recover on the next successful poll; check the log |
| A sensor you expected is missing | The pump reported it as not fitted (`US=0`) or returned no value during the first poll | Expected. If you add the hardware later, reload the integration (⋮ → Reload) to re-run discovery |
| A **Controls** section, or editable fields, appear | Leftovers from an earlier write-capable test build that Home Assistant still remembers | Delete the integration (⋮ → Delete), restart, add it again |

For details, enable debug logging for the integration (Settings → Devices &
Services → Heliotherm → ⋮ → Enable debug logging), reproduce the issue, then
disable it again to download the log. The log shows the discovery result, e.g.
`Discovery complete: 22/26 MP and 29/35 SP parameters supported`.

## 7. Updating

1. Open **HACS**, find **Heliotherm Heat Pump (Read-Only)**.
2. If HACS offers an **Update**, install it.
   This repository has no GitHub Releases, so HACS tracks the latest commit on
   `main` and may not always show an update badge. If there isn't one, open the
   integration in HACS → **⋮ → Redownload** — this fetches whatever is on `main`.
3. **Restart Home Assistant.** Python files under `custom_components/` are only
   reloaded on a full restart.

Your configuration, entities and history carry over.

## 8. Uninstalling

1. **Settings → Devices & Services → Heliotherm Heat Pump (Read-Only) → ⋮ →
   Delete.** This removes the device and all its entities.
2. **HACS** → the integration → **⋮ → Remove**.
3. Restart Home Assistant.

Nothing on the heat pump or the converter needs undoing: the integration only
ever read from it.
