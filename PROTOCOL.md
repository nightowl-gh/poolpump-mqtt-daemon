# Phnix Pool Heat Pump - Binary Protocol Specification

Reverse engineered from the Hayward/Trigms Android app (decompiled APK).

## Overview

- **Transport**: TCP socket connection  
- **Default port**: Inferred from app (set at connection time)  
- **Framing**: Fixed-length packets with CRC-16 trailer  
- **Byte order**: Big-endian  
- **Temperature encoding**: `raw_byte = (temp_celsius * 2) + 60` → decode: `temp = (raw_byte - 60) / 2.0`

## WiFi Module

The heat pump uses a **Beijing Simple-WiFi** module (Hi-Flying HF-series compatible) as a UART↔TCP bridge.

| Parameter | Value |
|-----------|-------|
| **Manufacturer** | Beijing Simple-WiFi Co.Ltd (© 2012) |
| **Web interface** | `http://<device-ip>/` |
| **Credentials** | `admin` / `123456` |
| **UART Baud Rate** | 38400 |
| **UART Data Format** | 8 data bits, no parity, 1 stop bit (8N1) |
| **UART Flow Control** | None |
| **Port Type** | UART (not SPI/SSI) |
| **Data Trigger Length** | 32–1024 bytes (buffer threshold before TCP send) |
| **Login Password** | 6 characters (`123456`) |
| **Socket 1 (local)** | TCP Server, port 60000 |
| **Socket 2 (cloud)** | TCP Client → `www.PhnixSmart.com:80` |
| **TCP Link Timeout** | 120 seconds |
| **Power Save Mode** | Low |

Architecture:

```
[Heat Pump MCU] ←— UART 38400 8N1 —→ [Simple-WiFi Module] ←— TCP:60000 —→ [Local client]
                                              ↕
                                     TCP:80 → www.PhnixSmart.com (cloud)
```

## Packet Structure

All packets share a common header:

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 1 | Magic1 | Always `0xAA` |
| 1 | 1 | Magic2 | Always `0x5A` |
| 2 | 1 | Kind Code | Device type identifier (e.g. `0xB1`) |
| 3 | 1 | Command Type | Direction/type of message |
| 4 | 1 | Sub-Command | Specific operation |
| 5-10 | 6 | MAC Address | Device MAC (6 bytes, from hex string pairs) |
| 11+ | varies | Payload | Command-specific data |
| N-2 | 1 | CRC High | CRC-16 high byte |
| N-1 | 1 | CRC Low | CRC-16 low byte |

### Packet Sizes

- **35 bytes** (33 data + 2 CRC): Status/control packets
- **48 bytes** (46 data + 2 CRC): Extended control packets  
- **79 bytes** (77 data + 2 CRC): Graph/history data packets

## Command Types (byte[3])

| Value | Direction | Description |
|-------|-----------|-------------|
| `0x83` | App → Device | Write/Request command |
| `0x80` | Device → App | Response to `0x83` |
| `0xD0` | Device → App | Status/notification push |
| `0xD2` | App → Device | Time sync command |

## Sub-Commands (byte[4])

### Requests (Command Type `0x83`) / Responses (`0x80`)

| Sub-Cmd | Description | Packet Size |
|---------|-------------|-------------|
| `0x00` | Factory parameters read/write | 48 bytes |
| `0x01` | Main control (power, mode, temp, timers) | 35 bytes |
| `0x03` | Set machine name | 48 bytes |
| `0x04` | Set barcode/verification code | 48 bytes |
| `0x05` | Set WiFi SSID (scan/connect) | 48 bytes |
| `0x06` | WiFi MAC/info response | 48 bytes |
| `0x07` | Set WiFi password | 79 bytes |
| `0xFF` | Special commands (upload/download/quit AP) | 48 bytes |

### Notifications (Command Type `0xD0`)

| Sub-Cmd | Description |
|---------|-------------|
| `0x00` | Graph/history data, device operating status |
| `0x01` | Real-time status (defrost, temps, faults) |

### Time Sync (Command Type `0xD2`)

| Sub-Cmd | Description |
|---------|-------------|
| `0x0F` | Synchronize date/time |

---

## Detailed Packet Formats

### Main Control Packet (`0x83 0x01`) — 35 bytes

Sent periodically from app to device. Also used as the primary status response (`0x80 0x01`) from device.

| Offset | Field | Encoding |
|--------|-------|----------|
| 0-1 | Magic | `AA 5A` |
| 2 | Kind Code | e.g. `B1` |
| 3 | Command | `83` (request) / `80` (response) |
| 4 | Sub-command | `01` |
| 5-10 | MAC | 6 hex bytes |
| 11 | Power | `00` = OFF, `01` = ON |
| 12 | Mode | See mode table below |
| 13 | Mode Select | `03`=cool, `06`=normal, `0C`=heat |
| 14 | Cool Temp | `(temp * 2) + 60` |
| 15 | Heat Temp | `(temp * 2) + 60` |
| 16 | Auto Temp | `(temp * 2) + 60` |
| 17 | Cool Max | `(temp * 2) + 60` |
| 18 | Cool Min | `(temp * 2) + 60` |
| 19 | Heat Max | `(temp * 2) + 60` |
| 20 | Heat Min | `(temp * 2) + 60` |
| 21 | Auto Max | `(temp * 2) + 60` |
| 22 | Auto Min | `(temp * 2) + 60` |
| 23 | Cool Backlash | Raw hex value |
| 24 | Heat Backlash | Raw hex value |
| 25 | Special Byte 1 | Bitfield (see below) |
| 26 | Special Byte 2 | Bitfield (see below) |
| 27 | Field _8027 | Unknown |
| 28 | Field _8028 | Unknown |
| 29 | Field _8029 | Unknown |
| 30 | Hot Water Temp | `(temp * 2) + 60` |
| 31 | Hot Water Max | `(temp * 2) + 60` |
| 32 | Hot Water Min | `(temp * 2) + 60` |
| 33-34 | CRC-16 | See CRC section |

### Mode Values (byte[12])

| Value | Mode |
|-------|------|
| `0x00` | Cool |
| `0x01` | Heat |
| `0x02` | Auto |
| `0x03` | Rapid Heat |
| `0x04` | Kitchen |
| `0x05` | Eco Heating |
| `0x06` | Normal Heat |
| `0x07` | Intelligent |
| `0x08` | Peak Mode |
| `0x09` | Vacation Mode |
| `0x0A` | Hot Water |
| `0x0B` | Cool + Hot Water |
| `0x0C` | Heat + Hot Water |

### Special Byte 1 (byte[25]) — Bitfield

| Bit | Description |
|-----|-------------|
| 0-3 | Remote parameter mode (0=12, 4=5, 5=12, 12=4) |
| 4 | Remote download flag |
| 5 | Remote download toggle |

### Special Byte 2 (byte[26]) — Bitfield

| Bit | Description |
|-----|-------------|
| 0 | Silent timer ON/OFF |
| 1 | Silent timer toggle |
| 4 | Fan open |
| 5 | Water pump open |

---

### Factory Parameters Packet (`0x83 0x00` / `0x80 0x00`) — 48 bytes

| Offset | Field | Description |
|--------|-------|-------------|
| 0-10 | Header | Standard header |
| 11 | Param Group | See table below |
| 12 | Param Count | Number of parameters |
| 13 | Param Begin | Start index (usually `0x01`) |
| 14 | Param End | End count |
| 15-44 | Parameters | Group-specific data |
| 45-46 | CRC-16 | |

#### Parameter Groups

| Group | Name | Description |
|-------|------|-------------|
| `0x21` (33) | Timer | Timer schedules |
| `0x44` (68) | D | Factory D (temps + ints) |
| `0x45` (69) | E | Factory E (RPM/timing) |
| `0x46` (70) | F | Factory F (defrost + silence timer) |
| `0x48` (72) | H | Factory H |
| `0x4B` (75) | K | Factory K |
| `0x4F` (79) | O | Speed/compressor/output |
| `0x50` (80) | P | Factory P |
| `0x52` (82) | R | Factory R (11 temperatures) |
| `0x53` (83) | S | Factory S |
| `0x54` (84) | T | Factory T (5 internal temps) |

#### Timer Parameters (Group `0x21`)

| Offset | Field | Description |
|--------|-------|-------------|
| 15 | Timer 1 Start Enable | `00`/`01` |
| 16 | Timer 1 Start Hour | 0-23 |
| 17 | Timer 1 Start Minute | 0-59 |
| 18 | Timer 1 End Enable | `00`/`01` |
| 19 | Timer 1 End Hour | 0-23 |
| 20 | Timer 1 End Minute | 0-59 |
| 21 | Timer 2 Start Enable | `00`/`01` |
| 22 | Timer 2 Start Hour | 0-23 |
| 23 | Timer 2 Start Minute | 0-59 |
| 24 | Timer 2 End Enable | `00`/`01` |
| 25 | Timer 2 End Hour | 0-23 |
| 26 | Timer 2 End Minute | 0-59 |

#### Factory Group D (`0x44`)

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | D01 | Temperature `(val-60)/2` |
| 16 | D02 | Temperature `(val-60)/2` |
| 17 | D03 | Raw integer |
| 18 | D04 | Raw integer |
| 19 | D05 | Raw integer |
| 20 | D06 | Raw hex |

#### Factory Group E (`0x45`)

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | E01 | Raw hex |
| 16 | E02 | Temperature `(val-60)/2` |
| 17 | E03 | `value × 10` (RPM/time) |
| 18 | E04 | `value × 10` |
| 19 | E05 | `value × 10` |
| 20 | E06 | `value × 10` |
| 21 | E07 | Raw integer |

#### Factory Group F (`0x46`) — Defrost + Silent Timer

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | F01 | Raw hex (defrost mode) |
| 16-21 | F02-F06 | Temperatures `(val-60)/2` |
| 22 | F08 | Hours (integer) |
| 23 | F09 | Hours (integer) |
| 24-27 | F10-F13 | Raw integers |
| 28 | Silent timer enabled | `00`/`01` |
| 29 | Silent start hour | 0-23 |
| 30 | Silent start minute | 0-59 |
| 31 | Silent end hour | 0-23 |
| 32 | Silent end minute | 0-59 |

Note: byte[12] (count) >10 indicates "long F mode" (18 params) vs "short F mode" (10 params).

#### Factory Group H (`0x48`)

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | H01 | Raw hex |
| 16 | H02 | Raw hex |
| 17 | H03 | Raw hex |
| 18 | H04 | Temperature `(val-60)/2` |

#### Factory Group P (`0x50`)

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | P01 | Raw hex |
| 16 | P02 | Integer |
| 17 | P03 | Integer |
| 18 | P04 | Integer |

#### Factory Group R (`0x52`) — Reference Temperatures

| Offset | Field | Encoding |
|--------|-------|----------|
| 15-25 | R01-R11 | All temperatures `(val-60)/2` |

#### Factory Group O (`0x4F`) — Speed/Compressor

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | Compressor | `0x00`=OFF, `0x01`=ON |
| 16-19 | O02-O05 | Raw hex |
| 20 | O06 | `value × 2` (current/frequency) |
| 23-24 | Speed | `byte[23]×256 + byte[24]` (16-bit RPM) |
| 25-26 | O07 | `byte[25]×256 + byte[26]` (16-bit) |
| 27-28 | O08 | `byte[27]×256 + byte[28]` (16-bit) |

#### Factory Group T (`0x54`) — Internal Temperatures

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | T01 (suction) | Temperature `(val-60)/2` |
| 16 | T02 | Temperature `(val-60)/2` |
| 17 | T03 (discharge) | Temperature `(val-60)/2` |
| 18 | T04 (coil) | Temperature `(val-60)/2` |
| 19 | T05 | Temperature `(val-60)/2` |

---

### Real-time Status (`0xD0 0x01`) — 35 bytes

Pushed from device to app with current operating status.

| Offset | Field | Encoding |
|--------|-------|----------|
| 11 | Defrost Status | Hex value (operating state indicator) |
| 12 | Inlet Temperature | `(val - 60) / 2.0` °C |
| 13 | Outlet Temperature | `(val - 60) / 2.0` °C |
| 14 | Ambient Temperature | `(val - 60) / 2.0` °C |
| 15 | Device Status | `(val - 60) / 2.0` (discharge temp or state) |
| 16 | (gap) | Unused |
| 17 | Output Status | Bitfield — relay/output states |
| 18-19 | (gap) | Unused |
| 20 | Fault Code Order | Hex value (0 = no fault) |
| 21-24 | Fault Code Data (4 bytes) | ASCII chars (e.g. "E01\0") |
| 25 | Fault Year | Value as decimal (year - 2000) |
| 26 | Fault Month | Value as decimal |
| 27 | Fault Day | Value as decimal |
| 28 | Fault Hour | Value as decimal |
| 29 | Fault Minute | Value as decimal |
| 30 | Special State | Hex value (combined operating state) |

#### Fault Codes

The fault code message is assembled from bytes 21-24 as a 4-character ASCII string
(trimmed). The following codes are defined (confirmed from APK v2.3 string resources):

| Code | Description |
|------|-------------|
| E01 | High pressure protection |
| E02 | Low pressure protection |
| E03 | Water flow failure |
| E06 | Excess temp. difference protection |
| E07 | Anti-freeze protection |
| E08 | Communication failure |
| E19 | Anti-freeze protection level 1 |
| E29 | Anti-freeze protection level 2 |
| P01 | Temp. sensor failure water inlet |
| P02 | Temp. sensor failure water outlet |
| P04 | Temp. sensor failure outdoor |
| P05 | Temp. sensor failure coil |
| P07 | Temp. sensor failure suction |

---

### Graph/History Data (`0xD0 0x00`)

Sub-types identified by byte[11]:

| byte[11] | Description |
|----------|-------------|
| `0x23` | Outlet water temperature history |
| `0x24` | Inlet water temperature history |
| `0x4F` | Compressor/speed/operating status |
| `0x53` | S parameters (raw) |
| `0x54` | T parameters (internal temperatures) |

#### History sub-types (`0x23`, `0x24`)

| Offset | Field |
|--------|-------|
| 11 | Data type (`0x23` or `0x24`) |
| 12 | Data count |
| 13 | Page number (`0x01` = first page, `0x02` = second) |
| 14 | Reserved |
| 15-N | Temperature data points, each encoded as `(val - 60) / 2.0` |

For 79-byte packets: 62 data points total (31 per page).  
For single-page (if packet is 79 bytes with count=62): all 62 in one packet.

#### Operating Status sub-type (`0x4F`)

| Offset | Field | Encoding |
|--------|-------|----------|
| 12 | Count | If >6 → extended mode with speed data |
| 15 | Compressor | `0x00`=OFF, `0x01`=ON |
| 16 | O02 | Raw hex |
| 17 | O03 | Raw hex |
| 18 | O04 | Raw hex |
| 19 | O05 | Raw hex |
| 20 | O06 | `value × 2` (current/frequency) |
| 23-24 | Speed | `byte[23]×256 + byte[24]` (16-bit RPM) |
| 25-26 | O07 | `byte[25]×256 + byte[26]` (16-bit) |
| 27-28 | O08 | `byte[27]×256 + byte[28]` (16-bit) |

#### S Parameters sub-type (`0x53`)

| Offset | Field |
|--------|-------|
| 12 | Count |
| 15-N | S parameter values (raw hex bytes) |

#### T Parameters sub-type (`0x54`) — Internal Temperatures

| Offset | Field | Encoding |
|--------|-------|----------|
| 15 | T01 (suction) | `(val - 60) / 2.0` °C |
| 16 | T02 | `(val - 60) / 2.0` °C |
| 17 | T03 (discharge) | `(val - 60) / 2.0` °C |
| 18 | T04 (coil) | `(val - 60) / 2.0` °C |
| 19 | T05 | `(val - 60) / 2.0` °C |

---

### WiFi SSID Packet (`0x83 0x05`) — 48 bytes

| Offset | Field |
|--------|-------|
| 0-10 | Standard header |
| 11 | `0x30` identifier |
| 12 | SSID length |
| 13 | `0x00` reserved |
| 14-45 | SSID (ASCII, zero-padded to 32 bytes) |
| 46-47 | CRC-16 |

### WiFi Password Packet (`0x83 0x07`) — 79 bytes

| Offset | Field |
|--------|-------|
| 0-10 | Standard header |
| 11 | `0x31` identifier |
| 12 | Password length |
| 13 | Security type (hex of numeric string) |
| 14-76 | Password (ASCII, zero-padded to 63 bytes) |
| 77-78 | CRC-16 |

---

### Machine Name Packet (`0x83 0x03`) — 48 bytes

| Offset | Field |
|--------|-------|
| 0-10 | Standard header |
| 11 | `0x00` |
| 12 | Name length (hex) |
| 13 | `0x00` reserved |
| 14-45 | Name (ASCII, zero-padded) |
| 46-47 | CRC-16 |

Response (`0x80 0x03`): bytes[14-45] contain the 32-byte machine name (ASCII).

### Barcode/Serial Packet (`0x83 0x04`) — 48 bytes

| Offset | Field |
|--------|-------|
| 0-10 | Standard header |
| 11+ | barcode_length + barcode_data (20 bytes padded) |
| 32+ | verifi_code_length + verifi_code_data (10 bytes padded) |
| trailing | `00 00 00` |
| 46-47 | CRC-16 |

Response (`0x80 0x04`):
- byte[11] = barcode length
- bytes[12..31] = barcode (ASCII, up to 20 chars)
- byte[32] = verification code length
- bytes[33+] = verification code (ASCII)

---

### Time Sync Packet (`0xD2 0x0F`) — 35 bytes

| Offset | Field |
|--------|-------|
| 0-10 | Standard header |
| 11-19 | Zeroed |
| 20 | Year (hex, year - 2000) |
| 21 | Month (hex, 1-12) |
| 22 | Day (hex) |
| 23 | Hour (hex) |
| 24 | Minute (hex) |
| 25-32 | Zeroed |
| 33-34 | CRC-16 |

---

### Special Command Packet (`0x83 0xFF`) — 48 bytes

| Offset | Field |
|--------|-------|
| 0-10 | Standard header |
| 11-14 | Command code (repeated) |
| 15-45 | Zeroed |
| 46-47 | CRC-16 |

Command codes:
- `0x33` — Quit AP mode
- `0x55` — Upload parameters (local)
- `0x66` — Download parameters (local)

---

## CRC-16 Calculation

The protocol uses **CRC-16/MODBUS** with lookup tables.

### Algorithm (pseudocode):

```
crc_high = 0xFF
crc_low = 0xFF

for each byte in data[0..length-3]:  # exclude last 2 CRC bytes
    index = (crc_high XOR byte) AND 0xFF
    crc_high = crc_low XOR TABLE_HIGH[index]
    crc_low = TABLE_LOW[index]

result = ((crc_high << 8) | (crc_low & 0xFF)) & 0xFFFF
packet[length-2] = (result >> 8) & 0xFF   # high byte
packet[length-1] = result & 0xFF          # low byte
```

### CRC Tables

**TABLE_HIGH** (256 bytes):
```
0x00 0xC1 0x81 0x40 0x01 0xC0 0x80 0x41 0x01 0xC0 0x80 0x41 0x00 0xC1 0x81 0x40
0x01 0xC0 0x80 0x41 0x00 0xC1 0x81 0x40 0x00 0xC1 0x81 0x40 0x01 0xC0 0x80 0x41
... (standard CRC-16/MODBUS high table)
```

**TABLE_LOW** (256 bytes):
```
0x00 0xC0 0xC1 0x01 0xC3 0x03 0x02 0xC2 0xC6 0x06 0x07 0xC7 0x05 0xC5 0xC4 0x04
... (standard CRC-16/MODBUS low table)
```

---

## Temperature Encoding

All temperature values use the same encoding:

```
Encoded = (temperature_celsius × 2) + 60
Decoded = (encoded_byte - 60) / 2.0
```

Examples:
- 25°C → `(25*2)+60 = 110 = 0x6E`
- 30°C → `(30*2)+60 = 120 = 0x78`
- 0°C → `(0*2)+60 = 60 = 0x3C`
- -10°C → `(-10*2)+60 = 40 = 0x28`

Range: -30°C (`0x00`) to +97.5°C (`0xFF`)

---

## Communication Flow

The device **continuously streams all data** on port 60000 without needing requests.
A passive TCP connection is sufficient to receive full state.

### Request / Response Mapping

| App Sends | Device Responds | Purpose |
|-----------|-----------------|---------|
| `0x83/0x01` | `0x80/0x01` | Control state + get status echo |
| `0x83/0x00` | `0x80/0x00` | Write/read factory parameters |
| `0x83/0x03` | `0x80/0x03` | Set/get machine name |
| `0x83/0x04` | `0x80/0x04` | Set/get barcode + verification |
| `0x83/0x05` | `0x80/0x05` | Set/get WiFi SSID |
| `0x83/0x07` | `0x80/0x07` | Set WiFi password |
| `0x83/0xFF` | (none) | Special commands |
| `0xD2/0x0F` | (none) | Time sync |
| (auto) | `0xD0/0x01` | Real-time telemetry push |
| (auto) | `0xD0/0x00` | Graph/history/operating data push |

### Keepalive

There is no dedicated heartbeat packet. The app sends `0x83/0x01` (control state)
every ~8 seconds to keep the connection alive and receive fresh state as `0x80/0x01`.
The device also pushes `0xD0` packets autonomously once connected.

1. **Client connects** via TCP to device IP:60000
2. **Device immediately starts broadcasting** all packet types in a cycle (~8s interval):
   - `0x80 0x01` — Main status (power, mode, set temps)
   - `0xD0 0x01` — Real-time (inlet, outlet, ambient temps, faults)
   - `0xD0 0x00` — Operating data (compressor, graphs, factory params)
3. **Control** (optional): Client sends `0x83 0x01` with full state to change settings
4. **WiFi setup** (one-time): Uses `0x83/0x05` + `0x83/0x07` + `0x83/0xFF` sequence in AP mode

### Timing (validated from live capture)

| Parameter | Value |
|-----------|-------|
| Broadcast cycle | ~8 seconds (all message types per cycle) |
| Messages per cycle | ~14 distinct packets |
| Connect timeout | 10 seconds (recommended) |
| Read timeout | 20 seconds (>2× cycle, detects power loss) |
| Reconnect backoff | 5s → 10s → 20s → ... → 300s max |

## Device Kind Codes

| Code | Description |
|------|-------------|
| `0xB1` | Main heat pump model (has factory params D,E,F,H,P,R) |
| Others | May have different parameter sets |

## WiFi Module Setup Procedure

The WiFi module has two operating modes:
- **AP mode** (initial setup): Broadcasts open network `Simple-WiFi`, module IP = `192.168.2.1`
- **Station mode** (normal): Connected to home WiFi, streams data on port `60000`

### Setup Flow

```
┌──────────────┐                    ┌──────────────┐
│   Phone/PC   │                    │  WiFi Module │
│              │                    │  (AP mode)   │
└──────┬───────┘                    └──────┬───────┘
       │                                   │
       │  1. Connect to "Simple-WiFi" AP   │
       │──────────────────────────────────>│
       │                                   │
       │  2. TCP connect 192.168.2.1:60000 │
       │──────────────────────────────────>│
       │                                   │
       │  3. Device sends status (learn MAC)│
       │<──────────────────────────────────│
       │                                   │
       │  4. Send 0x83/0x05 (Set SSID)     │
       │──────────────────────────────────>│
       │                                   │
       │  5. Wait 500ms                    │
       │                                   │
       │  6. Send 0x83/0x07 (Set Password) │
       │──────────────────────────────────>│
       │                                   │
       │  7. Wait 6s (device applies)      │
       │                                   │
       │  8. Verify readback matches       │
       │<──────────────────────────────────│
       │                                   │
       │  9. Wait 4s                       │
       │                                   │
       │ 10. Send 0x83/0xFF (Quit AP) ×10  │
       │──────────────────────────────────>│
       │                                   │
       │  Module exits AP, joins home WiFi │
       │                                   │
```

### Key Details

| Parameter | Value |
|-----------|-------|
| Module AP SSID | `Simple-WiFi` (open, no encryption) |
| Module AP IP | `192.168.2.1` |
| Port | `60000` (TCP socket, binary protocol) |
| Default password | `password` (fallback if none set) |
| Max SSID length | 32 bytes |
| Max password length | 63 bytes |
| Quit AP repeats | 10 times, 100ms apart |

### Security Type Values (byte[13] in 0x83/0x07)

| Value | Encryption |
|-------|-----------|
| `0x00` | Open (no password) |
| `0x01` | WEP-64 |
| `0x02` | WEP-128 |
| `0x03` | WPA/WPA2 |

### No HTTP/Web Interface

The WiFi module does **not** expose an HTTP web interface. All communication
(both setup and normal operation) uses the binary protocol over raw TCP on port 60000.

---

## Cloud Service (Remote Access)

The app can also communicate via a SOAP web service for remote monitoring:

| Parameter | Value |
|-----------|-------|
| Endpoint | `http://www.phnixsmart.com/Phnix.WaterHeater.WebService/SmartDeviceService.asmx` |
| Namespace | `http://www.phnix.cn/` |
| Auth UserId | `1001` |
| Auth Password | `Pa$$w0rd` |

### SOAP Operations

| Method | Purpose |
|--------|---------|
| `GetMachineStatus` | Read current device state |
| `MyMachineRemoteControl24H` | Send control commands |
| `GetWHTemperatureHistoryData` | Retrieve graph data |
| `RegistrationUserViaBarcode` | Register device to account |
| `GetPackageData` / `SavePackageData` | Sync configuration |
| `GetDuration` / `GetOnlineDuration` | Uptime statistics |

### FTP Log Upload

| Parameter | Value |
|-----------|-------|
| Server | `dev.3gmsc.com` |
| Username | `phnix` |
| Password | `px@3gms` |
| Directory | `Hayward_log` |

---

## Notes

- The app manufacturer is **Phnix** (品立信, Chinese HVAC company), rebranded as Hayward for pool market
- "Trigms" appears to be the app development company
- The WiFi module acts as AP for initial setup, then joins home network
- Chinese log messages confirm: "近程参数下载" = local param download, "远程上传" = remote upload
- "Izumi" temperature likely refers to the Japanese term for water source/spring (泉)
- Device streams ALL data on port 60000 without needing requests (passive monitoring)
- Broadcast cycle: ~14 message types repeated every ~8 seconds
