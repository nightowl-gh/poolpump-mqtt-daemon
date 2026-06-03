"""
Phnix Pool Heat Pump → MQTT Bridge Daemon

Connects to the heat pump's WiFi module on TCP port 60000,
parses the continuous binary data stream, and publishes
sensor values to MQTT with Home Assistant auto-discovery.

Also subscribes to MQTT command topics to control the pump
(power on/off, mode, set temperature).

Usage:
    python poolpump_mqtt.py --pump-host 192.168.1.123 --mqtt-host 192.168.1.x

Environment variables (alternative to CLI args):
    PUMP_HOST, PUMP_PORT, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt

log = logging.getLogger("poolpump")

# ─── CRC-16/Modbus ───────────────────────────────────────────────────────────

CRC_TABLE_HI = bytes([
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,
    0x00,0xC1,0x81,0x40,0x01,0xC0,0x80,0x41,0x01,0xC0,0x80,0x41,0x00,0xC1,0x81,0x40,
])

CRC_TABLE_LO = bytes([
    0x00,0xC0,0xC1,0x01,0xC3,0x03,0x02,0xC2,0xC6,0x06,0x07,0xC7,0x05,0xC5,0xC4,0x04,
    0xCC,0x0C,0x0D,0xCD,0x0F,0xCF,0xCE,0x0E,0x0A,0xCA,0xCB,0x0B,0xC9,0x09,0x08,0xC8,
    0xD8,0x18,0x19,0xD9,0x1B,0xDB,0xDA,0x1A,0x1E,0xDE,0xDF,0x1F,0xDD,0x1D,0x1C,0xDC,
    0x14,0xD4,0xD5,0x15,0xD7,0x17,0x16,0xD6,0xD2,0x12,0x13,0xD3,0x11,0xD1,0xD0,0x10,
    0xF0,0x30,0x31,0xF1,0x33,0xF3,0xF2,0x32,0x36,0xF6,0xF7,0x37,0xF5,0x35,0x34,0xF4,
    0x3C,0xFC,0xFD,0x3D,0xFF,0x3F,0x3E,0xFE,0xFA,0x3A,0x3B,0xFB,0x39,0xF9,0xF8,0x38,
    0x28,0xE8,0xE9,0x29,0xEB,0x2B,0x2A,0xEA,0xEE,0x2E,0x2F,0xEF,0x2D,0xED,0xEC,0x2C,
    0xE4,0x24,0x25,0xE5,0x27,0xE7,0xE6,0x26,0x22,0xE2,0xE3,0x23,0xE1,0x21,0x20,0xE0,
    0xA0,0x60,0x61,0xA1,0x63,0xA3,0xA2,0x62,0x66,0xA6,0xA7,0x67,0xA5,0x65,0x64,0xA4,
    0x6C,0xAC,0xAD,0x6D,0xAF,0x6F,0x6E,0xAE,0xAA,0x6A,0x6B,0xAB,0x69,0xA9,0xA8,0x68,
    0x78,0xB8,0xB9,0x79,0xBB,0x7B,0x7A,0xBA,0xBE,0x7E,0x7F,0xBF,0x7D,0xBD,0xBC,0x7C,
    0xB4,0x74,0x75,0xB5,0x77,0xB7,0xB6,0x76,0x72,0xB2,0xB3,0x73,0xB1,0x71,0x70,0xB0,
    0x50,0x90,0x91,0x51,0x93,0x53,0x52,0x92,0x96,0x56,0x57,0x97,0x55,0x95,0x94,0x54,
    0x9C,0x5C,0x5D,0x9D,0x5F,0x9F,0x9E,0x5E,0x5A,0x9A,0x9B,0x5B,0x99,0x59,0x58,0x98,
    0x88,0x48,0x49,0x89,0x4B,0x8B,0x8A,0x4A,0x4E,0x8E,0x8F,0x4F,0x8D,0x4D,0x4C,0x8C,
    0x44,0x84,0x85,0x45,0x87,0x47,0x46,0x86,0x82,0x42,0x43,0x83,0x41,0x81,0x80,0x40,
])


def crc16(data: bytes) -> int:
    crc_hi = 0xFF
    crc_lo = 0xFF
    for b in data:
        idx = (crc_hi ^ b) & 0xFF
        crc_hi = (crc_lo ^ CRC_TABLE_HI[idx]) & 0xFF
        crc_lo = CRC_TABLE_LO[idx]
    return ((crc_hi << 8) | (crc_lo & 0xFF)) & 0xFFFF


def build_packet(payload: bytes) -> bytes:
    crc = crc16(payload)
    return payload + struct.pack('>H', crc)


# ─── Temperature encoding ────────────────────────────────────────────────────

def decode_temp(b: int) -> float:
    return (b - 60) / 2.0


def encode_temp(celsius: float) -> int:
    return int(celsius * 2 + 60)


# ─── Protocol constants ──────────────────────────────────────────────────────

MODE_COOL = 0
MODE_HEAT = 1
MODE_AUTO = 2

MODE_NAMES = {0: "cool", 1: "heat", 2: "auto"}
MODE_FROM_NAME = {"cool": 0, "heat": 1, "auto": 2}

FAULT_DESCRIPTIONS = {
    "E01": "High pressure protection",
    "E02": "Low pressure protection",
    "E03": "Water flow failure",
    "E06": "Excess temp. difference protection",
    "E07": "Anti-freeze protection",
    "E08": "Communication failure",
    "E19": "Anti-freeze protection level 1",
    "E29": "Anti-freeze protection level 2",
    "P01": "Temp. sensor failure water inlet",
    "P02": "Temp. sensor failure water outlet",
    "P04": "Temp. sensor failure outdoor",
    "P05": "Temp. sensor failure coil",
    "P07": "Temp. sensor failure suction",
}


# ─── Parsed state ────────────────────────────────────────────────────────────

@dataclass
class PumpState:
    power: bool = False
    mode: int = 0
    mode_name: str = "off"
    heat_set: float = 0.0
    cool_set: float = 0.0
    auto_set: float = 0.0
    inlet_temp: float = 0.0
    outlet_temp: float = 0.0
    ambient_temp: float = 0.0
    compressor: bool = False
    fault_code: int = 0
    fault_msg: str = ""
    # Internal temps (from 0xD0/0x00 sub 0x54)
    suction_temp: float = 0.0
    discharge_temp: float = 0.0
    coil_temp: float = 0.0
    # Device info
    kind_code: int = 0
    mac: bytes = field(default_factory=lambda: b'\x00' * 6)
    mac_str: str = ""


# ─── MQTT topics ─────────────────────────────────────────────────────────────

TOPIC_PREFIX = "poolpump"
HA_DISCOVERY_PREFIX = "homeassistant"


def ha_sensor_config(name: str, unique_id: str, unit: str = None,
                     device_class: str = None, icon: str = None,
                     state_topic: str = None) -> dict:
    """Build HA MQTT discovery payload for a sensor."""
    config = {
        "name": name,
        "unique_id": unique_id,
        "state_topic": state_topic or f"{TOPIC_PREFIX}/sensor/{unique_id}/state",
        "availability_topic": f"{TOPIC_PREFIX}/status",
        "device": {
            "identifiers": ["phnix_pool_pump"],
            "name": "Pool Heat Pump",
            "manufacturer": "Phnix",
            "model": "Pool Heat Pump B1",
        },
    }
    if unit:
        config["unit_of_measurement"] = unit
    if device_class:
        config["device_class"] = device_class
    if icon:
        config["icon"] = icon
    return config


def ha_climate_config() -> dict:
    """Build HA MQTT discovery payload for a climate entity."""
    return {
        "name": "Pool Heat Pump",
        "unique_id": "phnix_pool_climate",
        "modes": ["off", "cool", "heat", "auto"],
        "min_temp": 8,
        "max_temp": 35,
        "temp_step": 0.5,
        "temperature_unit": "C",
        "current_temperature_topic": f"{TOPIC_PREFIX}/sensor/inlet_temp/state",
        "temperature_state_topic": f"{TOPIC_PREFIX}/climate/target_temp/state",
        "temperature_command_topic": f"{TOPIC_PREFIX}/climate/target_temp/set",
        "mode_state_topic": f"{TOPIC_PREFIX}/climate/mode/state",
        "mode_command_topic": f"{TOPIC_PREFIX}/climate/mode/set",
        "availability_topic": f"{TOPIC_PREFIX}/status",
        "device": {
            "identifiers": ["phnix_pool_pump"],
            "name": "Pool Heat Pump",
            "manufacturer": "Phnix",
            "model": "Pool Heat Pump B1",
        },
    }


# ─── Command builder ─────────────────────────────────────────────────────────

def build_time_sync_packet(state: PumpState) -> bytes:
    """Build 0xD2/0x0F time sync packet (35 bytes) with current local time."""
    now = time.localtime()
    payload = bytearray(33)
    payload[0] = 0xAA
    payload[1] = 0x5A
    payload[2] = state.kind_code
    payload[3] = 0xD2
    payload[4] = 0x0F
    payload[5:11] = state.mac
    # Bytes 11-19 zeroed
    payload[20] = now.tm_year - 2000
    payload[21] = now.tm_mon
    payload[22] = now.tm_mday
    payload[23] = now.tm_hour
    payload[24] = now.tm_min
    # Bytes 25-32 zeroed
    return build_packet(bytes(payload))


def build_control_packet(state: PumpState, power: bool | None = None,
                         mode: int | None = None, temp: float | None = None) -> bytes:
    """Build 0x83/0x01 control packet (35 bytes)."""
    payload = bytearray(33)
    payload[0] = 0xAA
    payload[1] = 0x5A
    payload[2] = state.kind_code
    payload[3] = 0x83
    payload[4] = 0x01
    payload[5:11] = state.mac

    p = power if power is not None else state.power
    m = mode if mode is not None else state.mode

    payload[11] = 0x01 if p else 0x00
    payload[12] = m

    # Set temperatures
    heat = state.heat_set
    cool = state.cool_set
    auto = state.auto_set

    if temp is not None:
        if m == MODE_HEAT:
            heat = temp
        elif m == MODE_COOL:
            cool = temp
        elif m == MODE_AUTO:
            auto = temp

    payload[14] = encode_temp(cool)
    payload[15] = encode_temp(heat)
    payload[16] = encode_temp(auto)

    return build_packet(bytes(payload))


# ─── Packet parser ───────────────────────────────────────────────────────────

class PacketParser:
    """Parses the TCP stream into individual protocol packets."""

    HEADER = b'\xAA\x5A'
    KNOWN_SIZES = (35, 48, 79)
    MAX_PACKET = 79

    def __init__(self):
        self.buffer = bytearray()

    def _find_next_header(self, start: int = 2) -> int:
        """Find offset of next AA5A header after start, or -1."""
        return self.buffer.find(self.HEADER, start)

    def _sync_to_header(self) -> bool:
        """Advance buffer to start at AA5A. Returns False if no header found."""
        idx = self.buffer.find(self.HEADER)
        if idx == -1:
            self.buffer.clear()
            return False
        if idx > 0:
            del self.buffer[:idx]
        return True

    def feed(self, data: bytes) -> list:
        """Feed raw TCP data and return list of complete packets."""
        self.buffer.extend(data)
        packets = []

        while len(self.buffer) >= 5:
            if not self._sync_to_header():
                break

            next_idx = self._find_next_header()
            if next_idx != -1:
                packets.append(bytes(self.buffer[:next_idx]))
                del self.buffer[:next_idx]
            elif len(self.buffer) >= self.MAX_PACKET:
                pkt_len = self._guess_packet_length()
                packets.append(bytes(self.buffer[:pkt_len]))
                del self.buffer[:pkt_len]
            else:
                break  # Wait for more data

        return packets

    def _guess_packet_length(self) -> int:
        """Guess packet length from known protocol sizes."""
        for size in self.KNOWN_SIZES:
            if len(self.buffer) >= size:
                return size
        return self.MAX_PACKET


# ─── Main bridge daemon ──────────────────────────────────────────────────────

class PoolPumpMQTT:
    def __init__(self, pump_host: str, pump_port: int,
                 mqtt_host: str, mqtt_port: int,
                 mqtt_user: str | None = None, mqtt_pass: str | None = None,
                 no_mqtt: bool = False, debug: bool = False):
        self.pump_host = pump_host
        self.pump_port = pump_port
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_pass = mqtt_pass
        self.no_mqtt = no_mqtt
        self.debug = debug

        self.state = PumpState()
        self.running = False
        self.mqtt_connected = False
        self.pump_sock = None
        self.mqtt_client = None
        self.lock = threading.Lock()
        self._last_clock_sync = 0.0
        self._offline_since = 0.0  # Timestamp when pump disconnected (0 = connected)

    def start(self):
        self.running = True
        if not self.no_mqtt:
            self._setup_mqtt()
        self._pump_thread = threading.Thread(target=self._pump_loop,
                                            daemon=True, name="pump-reader")
        self._pump_thread.start()
        log.info("Daemon started")

    def stop(self):
        log.info("Shutting down...")
        self.running = False
        if not self.no_mqtt:
            self._publish_availability("offline")
        if self.pump_sock:
            self.pump_sock.close()
        if self.mqtt_client:
            self.mqtt_client.disconnect()

    # ─── MQTT ────────────────────────────────────────────────────────────

    def _setup_mqtt(self):
        self.mqtt_client = mqtt.Client(
            client_id="poolpump_bridge",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if self.mqtt_user:
            self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.mqtt_client.will_set(f"{TOPIC_PREFIX}/status", "offline", retain=True)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.reconnect_delay_set(min_delay=5, max_delay=300)
        try:
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        except OSError as e:
            log.error(f"MQTT broker unreachable ({self.mqtt_host}:{self.mqtt_port}): {e}")
            log.info("Will keep retrying in the background...")
        self.mqtt_client.loop_start()

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.error(f"MQTT connection refused: {reason_code}")
            return
        log.info("MQTT connected")
        self.mqtt_connected = True
        self._publish_discovery()
        self._publish_availability("online")
        # Subscribe to command topics
        client.subscribe(f"{TOPIC_PREFIX}/climate/target_temp/set")
        client.subscribe(f"{TOPIC_PREFIX}/climate/mode/set")

    def _on_mqtt_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.mqtt_connected = False
        if reason_code != 0:
            log.warning(f"MQTT disconnected unexpectedly: {reason_code}")

    def _on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8').strip()
        log.info(f"MQTT command: {topic} = {payload}")

        try:
            if topic.endswith("/target_temp/set"):
                temp = float(payload)
                self._send_control(temp=temp)
            elif topic.endswith("/mode/set"):
                if payload == "off":
                    self._send_control(power=False)
                else:
                    mode = MODE_FROM_NAME.get(payload)
                    if mode is not None:
                        self._send_control(power=True, mode=mode)
        except (ValueError, KeyError) as e:
            log.error(f"Invalid command: {e}")

    def _send_control(self, power=None, mode=None, temp=None):
        with self.lock:
            if not self.pump_sock or self.state.kind_code == 0:
                log.warning("Cannot send control - not connected")
                return
            pkt = build_control_packet(self.state, power=power,
                                       mode=mode, temp=temp)
            try:
                self.pump_sock.sendall(pkt)
                log.info(f"Sent control: power={power} mode={mode} temp={temp}")
            except OSError as e:
                log.error(f"Send failed: {e}")

    def _publish_discovery(self):
        """Publish HA MQTT auto-discovery configs."""
        sensors = [
            ("Inlet Temperature", "inlet_temp", "°C", "temperature", None),
            ("Outlet Temperature", "outlet_temp", "°C", "temperature", None),
            ("Ambient Temperature", "ambient_temp", "°C", "temperature", None),
            ("Heat Set Point", "heat_set", "°C", "temperature", None),
            ("Cool Set Point", "cool_set", "°C", "temperature", None),
            ("Compressor", "compressor", None, None, "mdi:pump"),
            ("Fault Code", "fault_code", None, None, "mdi:alert-circle"),
            ("Fault Description", "fault_desc", None, None, "mdi:alert-circle-outline"),
        ]

        for name, uid, unit, dc, icon in sensors:
            config = ha_sensor_config(name, uid, unit, dc, icon)
            topic = f"{HA_DISCOVERY_PREFIX}/sensor/poolpump/{uid}/config"
            self.mqtt_client.publish(topic, json.dumps(config), retain=True)

        # Climate entity
        climate_config = ha_climate_config()
        topic = f"{HA_DISCOVERY_PREFIX}/climate/poolpump/pool_heat_pump/config"
        self.mqtt_client.publish(topic, json.dumps(climate_config), retain=True)

        log.info("Published HA discovery configs")

    def _publish_availability(self, status: str):
        self.mqtt_client.publish(f"{TOPIC_PREFIX}/status", status, retain=True)

    def _publish_state(self):
        """Publish current state to MQTT or print to console."""
        if self.no_mqtt:
            self._print_state()
            return
        if not self.mqtt_connected:
            return
        s = self.state
        pub = self.mqtt_client.publish

        pub(f"{TOPIC_PREFIX}/sensor/inlet_temp/state", f"{s.inlet_temp:.1f}", retain=True)
        pub(f"{TOPIC_PREFIX}/sensor/outlet_temp/state", f"{s.outlet_temp:.1f}", retain=True)
        pub(f"{TOPIC_PREFIX}/sensor/ambient_temp/state", f"{s.ambient_temp:.1f}", retain=True)
        pub(f"{TOPIC_PREFIX}/sensor/heat_set/state", f"{s.heat_set:.1f}", retain=True)
        pub(f"{TOPIC_PREFIX}/sensor/cool_set/state", f"{s.cool_set:.1f}", retain=True)
        pub(f"{TOPIC_PREFIX}/sensor/compressor/state",
            "ON" if s.compressor else "OFF", retain=True)
        fault_str = s.fault_msg if s.fault_msg else str(s.fault_code)
        pub(f"{TOPIC_PREFIX}/sensor/fault_code/state", fault_str, retain=True)
        desc = FAULT_DESCRIPTIONS.get(s.fault_msg, "") if s.fault_msg else ""
        pub(f"{TOPIC_PREFIX}/sensor/fault_desc/state", desc, retain=True)

        # Climate entity state
        if s.power:
            mode_str = MODE_NAMES.get(s.mode, "heat")
        else:
            mode_str = "off"
        pub(f"{TOPIC_PREFIX}/climate/mode/state", mode_str, retain=True)

        # Current target temp based on mode
        if s.mode == MODE_HEAT:
            target = s.heat_set
        elif s.mode == MODE_COOL:
            target = s.cool_set
        else:
            target = s.auto_set
        pub(f"{TOPIC_PREFIX}/climate/target_temp/state", f"{target:.1f}", retain=True)

    def _print_state(self):
        """Print current state to console."""
        s = self.state
        mode_str = MODE_NAMES.get(s.mode, "?") if s.power else "off"
        target = s.heat_set if s.mode == MODE_HEAT else (
            s.cool_set if s.mode == MODE_COOL else s.auto_set)
        fault_info = ""
        if s.fault_code:
            desc = FAULT_DESCRIPTIONS.get(s.fault_msg, "")
            fault_info = f" FAULT={s.fault_msg or s.fault_code}"
            if desc:
                fault_info += f" ({desc})"
        print(f"[{time.strftime('%H:%M:%S')}] "
              f"mode={mode_str} target={target:.1f}°C "
              f"inlet={s.inlet_temp:.1f}°C outlet={s.outlet_temp:.1f}°C "
              f"ambient={s.ambient_temp:.1f}°C "
              f"compressor={'ON' if s.compressor else 'OFF'}"
              f"{fault_info}")

    # ─── Pump TCP connection ─────────────────────────────────────────────

    RETRY_BASE = 5       # Initial retry delay (seconds)
    RETRY_MAX = 300      # Max retry delay (5 minutes)
    RECV_TIMEOUT = 20    # No data for 20s = connection dead (pump sends every ~8s)
    OFFLINE_GRACE = 60   # Seconds before publishing 'offline' to HA

    def _interruptible_sleep(self, seconds: int):
        """Sleep in 1s increments, returning early if stopped."""
        for _ in range(seconds):
            if not self.running:
                return
            time.sleep(1)

    def _close_pump_socket(self):
        """Close the pump socket if open."""
        if self.pump_sock:
            try:
                self.pump_sock.close()
            except OSError:
                pass
            self.pump_sock = None

    def _pump_loop(self):
        """Main loop: connect to pump, read stream, parse, publish."""
        retry_delay = self.RETRY_BASE

        while self.running:
            try:
                self._pump_connect()
                retry_delay = self.RETRY_BASE
                self._offline_since = 0.0
                self._publish_availability("online")
                self._read_stream()
            except (OSError, ConnectionError) as e:
                log.warning(f"Pump connection lost: {e}")
                if not self._offline_since:
                    self._offline_since = time.time()
                self._close_pump_socket()
                if self.running:
                    self._check_offline_grace()
                    log.info(f"Reconnecting in {retry_delay}s...")
                    self._interruptible_sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, self.RETRY_MAX)

    def _check_offline_grace(self):
        """Publish offline only after grace period has elapsed."""
        if self._offline_since and (
                time.time() - self._offline_since >= self.OFFLINE_GRACE):
            self._publish_availability("offline")

    def _read_stream(self):
        """Read and parse packets until disconnected."""
        parser = PacketParser()
        while self.running:
            data = self.pump_sock.recv(4096)
            if not data:
                raise ConnectionError("Connection closed by device")
            for pkt in parser.feed(data):
                self._handle_packet(pkt)

    def _pump_connect(self):
        log.info(f"Connecting to pump at {self.pump_host}:{self.pump_port}")
        self.pump_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pump_sock.settimeout(10)  # Connect timeout
        self.pump_sock.connect((self.pump_host, self.pump_port))
        self.pump_sock.settimeout(self.RECV_TIMEOUT)  # Read timeout
        log.info("Connected to pump")

    # (cmd, sub) -> (handler_method_name, min_packet_length)
    _PACKET_HANDLERS = {
        (0x80, 0x01): ('_parse_status', 33),
        (0xD0, 0x01): ('_parse_realtime', 31),
        (0xD0, 0x00): ('_parse_data', 20),
    }

    def _handle_packet(self, pkt: bytes):
        """Parse a single protocol packet and update state."""
        if len(pkt) < 12:
            return

        self._learn_device_identity(pkt)

        if self.debug:
            self._debug_print_packet(pkt)

        handler_info = self._PACKET_HANDLERS.get((pkt[3], pkt[4]))
        if handler_info is None:
            return
        method_name, min_len = handler_info
        if len(pkt) < min_len:
            return
        with self.lock:
            getattr(self, method_name)(pkt)

    # Factory parameter group names for debug output
    _PARAM_GROUPS = {
        0x21: "Timer", 0x44: "D", 0x45: "E", 0x46: "F",
        0x48: "H", 0x4B: "K", 0x4F: "O(speed)", 0x50: "P",
        0x52: "R", 0x53: "S", 0x54: "T(temps)",
    }

    # Extended mode names for debug (beyond cool/heat/auto)
    _ALL_MODES = {
        0: "cool", 1: "heat", 2: "auto", 3: "rapid_heat",
        4: "kitchen", 5: "eco_heat", 6: "normal_heat", 7: "intelligent",
        8: "peak", 9: "vacation", 10: "hot_water",
        11: "cool+hw", 12: "heat+hw",
    }

    def _debug_print_packet(self, pkt: bytes):
        """Print full hex dump and decoded fields for a packet."""
        ts = time.strftime('%H:%M:%S')
        cmd, sub = pkt[3], pkt[4]
        mac = ':'.join(f'{b:02x}' for b in pkt[5:11])
        hex_dump = pkt.hex(' ')
        print(f"\n[{ts}] PKT cmd=0x{cmd:02X} sub=0x{sub:02X} "
              f"len={len(pkt)} mac={mac}")
        print(f"  HEX: {hex_dump}")

        if cmd == 0x80 and sub == 0x01 and len(pkt) >= 33:
            self._debug_status(pkt)
        elif cmd == 0x80 and sub == 0x00 and len(pkt) >= 15:
            self._debug_factory(pkt)
        elif cmd == 0x80 and sub == 0x03 and len(pkt) >= 15:
            name = bytes(pkt[14:min(46, len(pkt))]).decode(
                'ascii', errors='replace').rstrip('\x00')
            print(f"  MACHINE_NAME: '{name}'")
        elif cmd == 0x80 and sub == 0x04 and len(pkt) >= 13:
            bc_len = min(pkt[11], 20)
            barcode = bytes(pkt[12:12 + bc_len]).decode(
                'ascii', errors='replace').rstrip('\x00')
            vc_off = 32
            vc_len = pkt[vc_off] if len(pkt) > vc_off else 0
            vcode = ""
            if vc_len and len(pkt) > vc_off + vc_len:
                vcode = bytes(pkt[vc_off + 1:vc_off + 1 + vc_len]).decode(
                    'ascii', errors='replace').rstrip('\x00')
            print(f"  BARCODE: '{barcode}' verify='{vcode}'")
        elif cmd == 0x80 and sub == 0x05 and len(pkt) >= 15:
            ssid = bytes(pkt[14:min(46, len(pkt))]).decode(
                'ascii', errors='replace').rstrip('\x00')
            print(f"  WIFI_SSID: '{ssid}'")
        elif cmd == 0x80 and sub == 0x06 and len(pkt) >= 15:
            info = bytes(pkt[14:min(46, len(pkt))]).decode(
                'ascii', errors='replace').rstrip('\x00')
            print(f"  WIFI_INFO: '{info}'")
        elif cmd == 0x80 and sub == 0x07 and len(pkt) >= 15:
            pw = bytes(pkt[14:min(77, len(pkt))]).decode(
                'ascii', errors='replace').rstrip('\x00')
            print(f"  WIFI_PASS: '{pw}'")
        elif cmd == 0x80 and sub == 0xFF and len(pkt) >= 15:
            code = pkt[11]
            labels = {0x33: "quit_AP", 0x66: "param_download", 0x55: "param_upload"}
            print(f"  SPECIAL: {labels.get(code, f'0x{code:02X}')}")
        elif cmd == 0xD0 and sub == 0x01 and len(pkt) >= 31:
            self._debug_realtime(pkt)
        elif cmd == 0xD0 and sub == 0x00 and len(pkt) >= 16:
            self._debug_data(pkt)
        elif cmd == 0xD2 and sub == 0x0F and len(pkt) >= 25:
            print(f"  TIME_SYNC: {pkt[20]+2000}-{pkt[21]:02d}-{pkt[22]:02d} "
                  f"{pkt[23]:02d}:{pkt[24]:02d}")
        else:
            print(f"  (no decoder for 0x{cmd:02X}/0x{sub:02X})")

    def _debug_status(self, pkt: bytes):
        mode_name = self._ALL_MODES.get(pkt[12], f'0x{pkt[12]:02X}')
        silent = "silent " if (pkt[26] & 0x01) else ""
        fan = "fan " if (pkt[26] & 0x10) else ""
        wpump = "wpump " if (pkt[26] & 0x20) else ""
        flags = (silent + fan + wpump).strip()
        print(f"  STATUS: power={'ON' if pkt[11]==1 else 'OFF'} "
              f"mode={mode_name} "
              f"cool={decode_temp(pkt[14]):.1f}[{decode_temp(pkt[18]):.0f}-"
              f"{decode_temp(pkt[17]):.0f}] "
              f"heat={decode_temp(pkt[15]):.1f}[{decode_temp(pkt[20]):.0f}-"
              f"{decode_temp(pkt[19]):.0f}] "
              f"auto={decode_temp(pkt[16]):.1f}[{decode_temp(pkt[22]):.0f}-"
              f"{decode_temp(pkt[21]):.0f}]")
        extras = []
        if pkt[23] or pkt[24]:
            extras.append(f"backlash=cool:{pkt[23]}/heat:{pkt[24]}")
        if pkt[30] != 60:  # hot water temp != 0°C means active
            extras.append(f"hw={decode_temp(pkt[30]):.1f}[{decode_temp(pkt[32]):.0f}-"
                          f"{decode_temp(pkt[31]):.0f}]")
        if flags:
            extras.append(f"flags=[{flags}]")
        if extras:
            print(f"         {' '.join(extras)}")

    def _debug_factory(self, pkt: bytes):
        group = pkt[11]
        group_name = self._PARAM_GROUPS.get(group, f"0x{group:02X}")
        count = pkt[12]
        data_end = min(15 + count, len(pkt) - 2)
        params = ' '.join(f'{b:02X}' for b in pkt[15:data_end])
        extra = ""
        if group == 0x4F and len(pkt) >= 21:
            comp = "ON" if pkt[15] == 1 else "OFF"
            extra = f" compressor={comp}"
            if count > 6 and len(pkt) >= 29:
                o06 = pkt[20] * 2
                speed = (pkt[23] << 8) | pkt[24]
                o07 = (pkt[25] << 8) | pkt[26]
                o08 = (pkt[27] << 8) | pkt[28]
                extra += (f" O06={o06} speed={speed} "
                          f"O07={o07} O08={o08}")
        elif group == 0x54 and len(pkt) >= 20:
            n = min(count, 5)
            temps = [f"{decode_temp(pkt[15+i]):.1f}" for i in range(n)]
            extra = f" T=[{','.join(temps)}]"
        elif group == 0x21 and len(pkt) >= 27:
            t1 = f"{pkt[16]:02d}:{pkt[17]:02d}" if pkt[15] else "off"
            t1e = f"{pkt[19]:02d}:{pkt[20]:02d}" if pkt[18] else "off"
            t2 = f"{pkt[22]:02d}:{pkt[23]:02d}" if pkt[21] else "off"
            t2e = f"{pkt[25]:02d}:{pkt[26]:02d}" if pkt[24] else "off"
            extra = f" timer1=[{t1}→{t1e}] timer2=[{t2}→{t2e}]"
        elif group == 0x44 and len(pkt) >= 21:
            extra = (f" D01={decode_temp(pkt[15]):.1f} D02={decode_temp(pkt[16]):.1f}"
                     f" D03={pkt[17]} D04={pkt[18]} D05={pkt[19]}")
        elif group == 0x45 and len(pkt) >= 22:
            extra = (f" E01=0x{pkt[15]:02X} E02={decode_temp(pkt[16]):.1f}"
                     f" E03={pkt[17]*10} E04={pkt[18]*10}"
                     f" E05={pkt[19]*10} E06={pkt[20]*10} E07={pkt[21]}")
        elif group == 0x46 and len(pkt) >= 28:
            extra = (f" F01=0x{pkt[15]:02X}"
                     f" F02-06=[{decode_temp(pkt[16]):.1f},"
                     f"{decode_temp(pkt[17]):.1f},{decode_temp(pkt[18]):.1f},"
                     f"{decode_temp(pkt[19]):.1f},{decode_temp(pkt[20]):.1f}]"
                     f" F08={pkt[22]}h F09={pkt[23]}h")
            if len(pkt) >= 33:
                sil = f"{pkt[29]:02d}:{pkt[30]:02d}→{pkt[31]:02d}:{pkt[32]:02d}"
                extra += f" silence=[{'on' if pkt[28] else 'off'} {sil}]"
        elif group == 0x48 and len(pkt) >= 19:
            extra = (f" H01=0x{pkt[15]:02X} H02=0x{pkt[16]:02X}"
                     f" H03=0x{pkt[17]:02X} H04={decode_temp(pkt[18]):.1f}")
        elif group == 0x50 and len(pkt) >= 19:
            extra = (f" P01=0x{pkt[15]:02X} P02={pkt[16]}"
                     f" P03={pkt[17]} P04={pkt[18]}")
        elif group == 0x52 and len(pkt) >= 26:
            n = min(count, 11)
            temps = [f"{decode_temp(pkt[15+i]):.1f}" for i in range(n)]
            extra = f" R=[{','.join(temps)}]"
        print(f"  FACTORY({group_name}): n={count} [{params}]{extra}")

    def _debug_realtime(self, pkt: bytes):
        fault_msg = ""
        if pkt[20] and len(pkt) > 24:
            fault_msg = bytes(pkt[21:25]).decode('ascii', errors='replace').strip('\x00')
        desc = FAULT_DESCRIPTIONS.get(fault_msg, "")
        fault_str = f" fault={fault_msg}({desc})" if fault_msg else ""
        fault_time = ""
        if fault_msg and len(pkt) > 29:
            fault_time = (f" @20{pkt[25]:02d}-{pkt[26]:02d}-{pkt[27]:02d}"
                          f" {pkt[28]:02d}:{pkt[29]:02d}")
        special = f" special=0x{pkt[30]:02X}" if len(pkt) > 30 and pkt[30] else ""
        print(f"  REALTIME: inlet={decode_temp(pkt[12]):.1f} "
              f"outlet={decode_temp(pkt[13]):.1f} "
              f"ambient={decode_temp(pkt[14]):.1f} "
              f"devstat={decode_temp(pkt[15]):.1f} "
              f"output=0x{pkt[17]:02X} defrost=0x{pkt[11]:02X}"
              f"{fault_str}{fault_time}{special}")

    def _debug_data(self, pkt: bytes):
        sub_type = pkt[11]
        count = pkt[12] if len(pkt) > 12 else 0
        if sub_type == 0x4F and len(pkt) >= 21:
            extra = f" compressor={'ON' if pkt[15]==1 else 'OFF'}"
            if count > 6 and len(pkt) >= 29:
                o06 = pkt[20] * 2
                speed = (pkt[23] << 8) | pkt[24]
                o07 = (pkt[25] << 8) | pkt[26]
                o08 = (pkt[27] << 8) | pkt[28]
                extra += f" O06={o06} speed={speed} O07={o07} O08={o08}"
            print(f"  DATA/4F:{extra}")
        elif sub_type == 0x54 and len(pkt) >= 20:
            n = min(count, 5)
            temps = [f"{decode_temp(pkt[15+i]):.1f}" for i in range(n)]
            print(f"  DATA/54: T=[{','.join(temps)}]"
                  f" (suction,?,discharge,coil,?)")
        elif sub_type == 0x53 and len(pkt) >= 16:
            vals = ' '.join(f'{pkt[15+i]:02X}' for i in range(min(count, 10)))
            print(f"  DATA/53: S=[{vals}]")
        elif sub_type in (0x23, 0x24):
            label = 'outlet_hist' if sub_type == 0x23 else 'inlet_hist'
            page = pkt[13] if len(pkt) > 13 else 0
            pts = min(count, len(pkt) - 15)
            if pts > 0:
                temps = [f"{decode_temp(pkt[15+i]):.1f}" for i in range(pts)]
                sample = ','.join(temps[:5])
                if pts > 5:
                    sample += f"...({pts} pts)"
                print(f"  DATA/{sub_type:02X}: {label} page={page} [{sample}]")
            else:
                print(f"  DATA/{sub_type:02X}: {label} page={page} count={count}")
        else:
            raw = ' '.join(f'{b:02X}' for b in pkt[15:min(len(pkt)-2, 30)])
            print(f"  DATA/0x{sub_type:02X}: n={count} [{raw}]")

    def _learn_device_identity(self, pkt: bytes):
        """Learn kind_code and MAC from the first packet received."""
        if self.state.kind_code != 0:
            return
        self.state.kind_code = pkt[2]
        self.state.mac = pkt[5:11]
        self.state.mac_str = ':'.join(f'{b:02x}' for b in pkt[5:11])
        log.info(f"Device: kind=0x{pkt[2]:02X} MAC={self.state.mac_str}")
        self._sync_clock()

    CLOCK_SYNC_INTERVAL = 86400  # Re-sync every 24 hours

    def _sync_clock(self):
        """Send time sync packet to set the pump's clock to local time."""
        if not self.pump_sock or self.state.kind_code == 0:
            return
        pkt = build_time_sync_packet(self.state)
        try:
            self.pump_sock.sendall(pkt)
            self._last_clock_sync = time.time()
            log.info(f"Sent time sync: {time.strftime('%Y-%m-%d %H:%M')}")
        except OSError as e:
            log.warning(f"Time sync failed: {e}")

    def _maybe_sync_clock(self):
        """Re-sync clock if 24 hours have passed since last sync."""
        if time.time() - self._last_clock_sync >= self.CLOCK_SYNC_INTERVAL:
            self._sync_clock()

    def _parse_status(self, pkt: bytes):
        """Parse 0x80/0x01 main status packet."""
        s = self.state
        prev_power = s.power
        prev_mode = s.mode
        prev_heat = s.heat_set

        s.power = pkt[11] == 1
        s.mode = pkt[12]
        s.mode_name = MODE_NAMES.get(s.mode, "unknown")
        s.cool_set = decode_temp(pkt[14])
        s.heat_set = decode_temp(pkt[15])
        s.auto_set = decode_temp(pkt[16])

        # Only publish if something changed or periodically
        if (s.power != prev_power or s.mode != prev_mode
                or s.heat_set != prev_heat):
            self._publish_state()
            log.debug(f"Status: power={s.power} mode={s.mode_name} "
                      f"heat={s.heat_set} cool={s.cool_set}")

    def _parse_realtime(self, pkt: bytes):
        """Parse 0xD0/0x01 realtime temperature packet."""
        s = self.state

        s.inlet_temp = decode_temp(pkt[12])
        s.outlet_temp = decode_temp(pkt[13])
        s.ambient_temp = decode_temp(pkt[14])
        s.fault_code = pkt[20] if len(pkt) > 20 else 0
        if s.fault_code and len(pkt) > 24:
            s.fault_msg = bytes(pkt[21:25]).decode('ascii', errors='replace').strip('\x00')
        else:
            s.fault_msg = ""

        # Publish on every realtime update (~8 sec cycle)
        self._publish_state()
        self._maybe_sync_clock()
        log.debug(f"Realtime: inlet={s.inlet_temp} outlet={s.outlet_temp} "
                  f"ambient={s.ambient_temp}")

    def _parse_data(self, pkt: bytes):
        """Parse 0xD0/0x00 data packets (device status, history, etc)."""
        if len(pkt) < 16:
            return
        sub_type = pkt[11]

        if sub_type == 0x4F and len(pkt) >= 21:
            # Device operating status
            self.state.compressor = pkt[15] == 0x01

        elif sub_type == 0x54 and len(pkt) >= 21:
            # Factory temperatures
            self.state.suction_temp = decode_temp(pkt[15])
            self.state.discharge_temp = decode_temp(pkt[17])
            self.state.coil_temp = decode_temp(pkt[18])


# ─── One-shot clock sync ─────────────────────────────────────────────────────

def _sync_clock_and_exit(host: str, port: int):
    """Connect to pump, wait for one packet to learn identity, send time sync, exit."""
    log.info(f"Connecting to {host}:{port} for clock sync...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((host, port))
    except OSError as e:
        log.error(f"Cannot connect: {e}")
        raise SystemExit(1)

    # Read until we get a packet with the device identity
    parser = PacketParser()
    sock.settimeout(15)
    state = PumpState()
    try:
        while state.kind_code == 0:
            data = sock.recv(4096)
            if not data:
                raise ConnectionError("Connection closed")
            for pkt in parser.feed(data):
                if len(pkt) >= 12 and state.kind_code == 0:
                    state.kind_code = pkt[2]
                    state.mac = pkt[5:11]
    except (OSError, ConnectionError) as e:
        log.error(f"Failed to identify device: {e}")
        sock.close()
        raise SystemExit(1)

    # Send time sync
    pkt = build_time_sync_packet(state)
    sock.sendall(pkt)
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    mac_str = ':'.join(f'{b:02x}' for b in state.mac)
    print(f"Clock synced to {now} (device MAC={mac_str})")
    sock.close()


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phnix Pool Heat Pump MQTT Bridge for Home Assistant")
    parser.add_argument('-d', '--daemon', action='store_true',
                        help='Run as daemon (uses env vars for defaults)')
    parser.add_argument('--sync-clock', action='store_true',
                        help='Sync pump clock to local time and exit')
    parser.add_argument('--no-mqtt', action='store_true',
                        help='Skip MQTT, print readings to console')
    parser.add_argument('--pump-host',
                        default=os.environ.get('PUMP_HOST'),
                        help='Heat pump IP (env: PUMP_HOST)')
    parser.add_argument('--pump-port', type=int,
                        default=int(os.environ.get('PUMP_PORT', '60000')),
                        help='Heat pump port (default: 60000)')
    parser.add_argument('--mqtt-host',
                        default=os.environ.get('MQTT_HOST'),
                        help='MQTT broker host (env: MQTT_HOST)')
    parser.add_argument('--mqtt-port', type=int,
                        default=int(os.environ.get('MQTT_PORT', '1883')),
                        help='MQTT broker port (default: 1883)')
    parser.add_argument('--mqtt-user',
                        default=os.environ.get('MQTT_USER'),
                        help='MQTT username')
    parser.add_argument('--mqtt-pass',
                        default=os.environ.get('MQTT_PASS'),
                        help='MQTT password')
    parser.add_argument('--debug', action='store_true',
                        help='Print full decoded packets to console')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    args = parser.parse_args()

    # In daemon mode, fall back to sensible defaults from env
    if args.daemon:
        if not args.pump_host:
            args.pump_host = '192.168.1.123'
        if not args.mqtt_host:
            args.mqtt_host = 'localhost'
    else:
        # Command-line mode: require connection parameters
        missing = []
        if not args.pump_host:
            missing.append('--pump-host')
        if not args.no_mqtt and not args.mqtt_host:
            missing.append('--mqtt-host')
        if missing:
            parser.error(f"Missing required arguments: {', '.join(missing)}\n"
                         "  Use -d/--daemon to run with env var defaults.")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    if args.sync_clock:
        _sync_clock_and_exit(args.pump_host, args.pump_port)
        return

    bridge = PoolPumpMQTT(
        pump_host=args.pump_host,
        pump_port=args.pump_port,
        mqtt_host=args.mqtt_host or '',
        mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user,
        mqtt_pass=args.mqtt_pass,
        no_mqtt=args.no_mqtt,
        debug=args.debug,
    )

    def handle_signal(signum, frame):
        bridge.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    bridge.start()

    # Keep main thread alive
    try:
        while bridge.running:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()


if __name__ == '__main__':
    main()
