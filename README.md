# Pool Heat Pump MQTT Bridge

MQTT bridge daemon that connects to a Phnix/Hayward pool heat pump's WiFi module
and exposes it to Home Assistant via MQTT auto-discovery.

## Features

- **Passive monitoring** — listens to the pump's continuous data stream (no polling)
- **Home Assistant auto-discovery** — climate entity + sensors appear automatically
- **Bidirectional control** — power on/off, mode selection, temperature adjustment
- **Graceful offline handling** — exponential backoff when pump power is cut (e.g. overnight)
- **Systemd service** — runs as a daemon on Linux

## Tested Hardware

| Brand | Model | WiFi Module | Status |
|-------|-------|-------------|--------|
| KMP | Premium 13 | Simple-WiFi (Hi-Flying) | ✅ Working |

These heat pumps are OEM'd by Phnix and sold under many brand names (Hayward, KMP, etc.).
If you have a different brand with the same WiFi module and protocol, please report your results.

## Requirements

- Python 3.10+
- `paho-mqtt` library
- MQTT broker (e.g. Mosquitto)
- Network access to the heat pump's WiFi module on port 60000

## Quick Start

```bash
pip install paho-mqtt

python poolpump_mqtt.py \
    --pump-host 192.168.1.123 \
    --mqtt-host 192.168.1.x
```

## Installation (Linux Server)

```bash
# Copy files
sudo mkdir -p /opt/poolpump
sudo cp poolpump_mqtt.py /opt/poolpump/

# Install dependency
pip3 install paho-mqtt

# Create service user
sudo useradd -r -s /usr/sbin/nologin poolpump

# Install config and systemd service
sudo cp poolpump-mqtt.default /etc/default/poolpump-mqtt
sudo cp poolpump-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now poolpump-mqtt
```

Verify it's running:
```bash
sudo systemctl status poolpump-mqtt
```

Follow the log output:
```bash
sudo journalctl -u poolpump-mqtt -f
```

### Configuration

Edit `/etc/default/poolpump-mqtt`:

```bash
PUMP_HOST=192.168.1.123
PUMP_PORT=60000
MQTT_HOST=localhost
MQTT_PORT=1883
#MQTT_USER=
#MQTT_PASS=
```

Then restart to apply:
```bash
sudo systemctl restart poolpump-mqtt
```

Alternatively, use CLI arguments:
```bash
python poolpump_mqtt.py --pump-host 192.168.1.123 --mqtt-host 10.0.0.5 --mqtt-user ha --mqtt-pass secret
```

## CLI Reference

| Option | Default | Env Variable | Description |
|--------|---------|--------------|-------------|
| `-d`, `--daemon` | — | — | Run as daemon (uses env vars for defaults) |
| `--sync-clock` | — | — | Sync pump clock to local time and exit |
| `--no-mqtt` | — | — | Skip MQTT, print readings to console |
| `--pump-host` | — | `PUMP_HOST` | Heat pump WiFi module IP address |
| `--pump-port` | `60000` | `PUMP_PORT` | Heat pump TCP port |
| `--mqtt-host` | — | `MQTT_HOST` | MQTT broker hostname/IP |
| `--mqtt-port` | `1883` | `MQTT_PORT` | MQTT broker port |
| `--mqtt-user` | — | `MQTT_USER` | MQTT username |
| `--mqtt-pass` | — | `MQTT_PASS` | MQTT password |
| `--debug` | — | — | Print full decoded packets to console |
| `--log-level` | `INFO` | — | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

CLI arguments take precedence over environment variables.

## Home Assistant Entities

Once connected, the following entities appear automatically in HA:

### Climate Entity

| Attribute | Value |
|-----------|-------|
| Entity ID | `climate.pool_heat_pump` |
| Modes | off, heat, cool, auto |
| Min temp | 8°C |
| Max temp | 35°C |
| Step | 0.5°C |

Use the thermostat card to control power, mode, and target temperature.

### Sensors

| Entity | Type | Unit |
|--------|------|------|
| Inlet Temperature | temperature | °C |
| Outlet Temperature | temperature | °C |
| Ambient Temperature | temperature | °C |
| Heat Set Point | temperature | °C |
| Cool Set Point | temperature | °C |
| Compressor | binary | ON/OFF |
| Fault Code | diagnostic | — |

## MQTT Topics

### Published (read)

| Topic | Payload |
|-------|---------|
| `poolpump/status` | `online` / `offline` |
| `poolpump/sensor/inlet_temp/state` | e.g. `27.5` |
| `poolpump/sensor/outlet_temp/state` | e.g. `31.0` |
| `poolpump/sensor/ambient_temp/state` | e.g. `24.0` |
| `poolpump/sensor/heat_set/state` | e.g. `28.0` |
| `poolpump/sensor/cool_set/state` | e.g. `20.0` |
| `poolpump/sensor/compressor/state` | `ON` / `OFF` |
| `poolpump/sensor/fault_code/state` | e.g. `0` |
| `poolpump/climate/mode/state` | `off` / `heat` / `cool` / `auto` |
| `poolpump/climate/target_temp/state` | e.g. `28.0` |

### Command (write from HA)

| Topic | Payload |
|-------|---------|
| `poolpump/climate/mode/set` | `off`, `heat`, `cool`, or `auto` |
| `poolpump/climate/target_temp/set` | e.g. `29.5` |

## Offline Behavior

The pump's power is typically cut overnight. The daemon handles this gracefully:

1. Detects connection loss within 20 seconds (recv timeout, since pump broadcasts every ~8s)
2. Publishes `offline` to `poolpump/status` — HA shows entity as "Unavailable"
3. Retries with exponential backoff: 5s → 10s → 20s → 40s → ... → 5min max
4. Reconnects automatically when pump powers back on
5. Resets backoff to 5s after successful connection

## Architecture

```
┌──────────────┐        TCP:60000         ┌──────────────┐
│  Heat Pump   │ ──── binary stream ────> │   poolpump   │
│  WiFi Module │ <── control packets ──── │   _mqtt.py   │
└──────────────┘                          └──────┬───────┘
                                                 │ MQTT
                                          ┌──────┴───────┐
                                          │  Mosquitto   │
                                          │   Broker     │
                                          └──────┬───────┘
                                                 │
                                          ┌──────┴───────┐
                                          │    Home      │
                                          │  Assistant   │
                                          └──────────────┘
```

## Protocol

See [PROTOCOL.md](PROTOCOL.md) for the full binary protocol specification.

## WiFi Module Setup

If the pump's WiFi module needs to be (re)configured to join your home network,
use the setup script:

```bash
# Connect your computer to the "Simple-WiFi" open AP first
python wifi_setup.py --ssid "YourNetwork" --password "YourWiFiPass" --name "Pool Pump"
```

See [PROTOCOL.md](PROTOCOL.md#wifi-module-setup-procedure) for details.

## Files

| File | Purpose |
|------|---------|
| `poolpump_mqtt.py` | MQTT bridge daemon |
| `poolpump-mqtt.service` | Systemd unit file |
| `poolpump-mqtt.default` | `/etc/default/poolpump-mqtt` config template |
| `wifi_setup.py` | WiFi module initial setup script |
| `PROTOCOL.md` | Binary protocol specification |
| `decode_capture.py` | Decode raw binary captures |
| `parse_pcap.py` | Parse Wireshark pcap files |
