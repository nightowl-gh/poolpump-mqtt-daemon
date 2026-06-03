"""
Phnix/Hayward Pool Heat Pump - WiFi Module Setup Script

This script configures the WiFi module on a Phnix pool heat pump.
It connects to the module's AP (Simple-WiFi) and sends commands to
configure home WiFi credentials, then tells the module to exit AP mode.

Setup procedure:
1. The WiFi module broadcasts an open AP named "Simple-WiFi"
2. Connect your computer to this AP
3. The module's IP is 192.168.2.1, port 60000 (TCP socket)
4. Run this script to send your home WiFi credentials
5. The module exits AP mode and joins your home network

Protocol: Binary packets over TCP, CRC-16/Modbus checksum.
"""

import socket
import struct
import time
import sys

# CRC-16/Modbus lookup tables (from C0559d.java)
CRC_TABLE_HI = bytes([
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
])

CRC_TABLE_LO = bytes([
    0x00, 0xC0, 0xC1, 0x01, 0xC3, 0x03, 0x02, 0xC2, 0xC6, 0x06, 0x07, 0xC7, 0x05, 0xC5, 0xC4, 0x04,
    0xCC, 0x0C, 0x0D, 0xCD, 0x0F, 0xCF, 0xCE, 0x0E, 0x0A, 0xCA, 0xCB, 0x0B, 0xC9, 0x09, 0x08, 0xC8,
    0xD8, 0x18, 0x19, 0xD9, 0x1B, 0xDB, 0xDA, 0x1A, 0x1E, 0xDE, 0xDF, 0x1F, 0xDD, 0x1D, 0x1C, 0xDC,
    0x14, 0xD4, 0xD5, 0x15, 0xD7, 0x17, 0x16, 0xD6, 0xD2, 0x12, 0x13, 0xD3, 0x11, 0xD1, 0xD0, 0x10,
    0xF0, 0x30, 0x31, 0xF1, 0x33, 0xF3, 0xF2, 0x32, 0x36, 0xF6, 0xF7, 0x37, 0xF5, 0x35, 0x34, 0xF4,
    0x3C, 0xFC, 0xFD, 0x3D, 0xFF, 0x3F, 0x3E, 0xFE, 0xFA, 0x3A, 0x3B, 0xFB, 0x39, 0xF9, 0xF8, 0x38,
    0x28, 0xE8, 0xE9, 0x29, 0xEB, 0x2B, 0x2A, 0xEA, 0xEE, 0x2E, 0x2F, 0xEF, 0x2D, 0xED, 0xEC, 0x2C,
    0xE4, 0x24, 0x25, 0xE5, 0x27, 0xE7, 0xE6, 0x26, 0x22, 0xE2, 0xE3, 0x23, 0xE1, 0x21, 0x20, 0xE0,
    0xA0, 0x60, 0x61, 0xA1, 0x63, 0xA3, 0xA2, 0x62, 0x66, 0xA6, 0xA7, 0x67, 0xA5, 0x65, 0x64, 0xA4,
    0x6C, 0xAC, 0xAD, 0x6D, 0xAF, 0x6F, 0x6E, 0xAE, 0xAA, 0x6A, 0x6B, 0xAB, 0x69, 0xA9, 0xA8, 0x68,
    0x78, 0xB8, 0xB9, 0x79, 0xBB, 0x7B, 0x7A, 0xBA, 0xBE, 0x7E, 0x7F, 0xBF, 0x7D, 0xBD, 0xBC, 0x7C,
    0xB4, 0x74, 0x75, 0xB5, 0x77, 0xB7, 0xB6, 0x76, 0x72, 0xB2, 0xB3, 0x73, 0xB1, 0x71, 0x70, 0xB0,
    0x50, 0x90, 0x91, 0x51, 0x93, 0x53, 0x52, 0x92, 0x96, 0x56, 0x57, 0x97, 0x55, 0x95, 0x94, 0x54,
    0x9C, 0x5C, 0x5D, 0x9D, 0x5F, 0x9F, 0x9E, 0x5E, 0x5A, 0x9A, 0x9B, 0x5B, 0x99, 0x59, 0x58, 0x98,
    0x88, 0x48, 0x49, 0x89, 0x4B, 0x8B, 0x8A, 0x4A, 0x4E, 0x8E, 0x8F, 0x4F, 0x8D, 0x4D, 0x4C, 0x8C,
    0x44, 0x84, 0x85, 0x45, 0x87, 0x47, 0x46, 0x86, 0x82, 0x42, 0x43, 0x83, 0x41, 0x81, 0x80, 0x40,
])

# Security types
SECURITY_OPEN = 0
SECURITY_WEP64 = 1
SECURITY_WEP128 = 2
SECURITY_WPA = 3


def crc16(data: bytes) -> int:
    """Calculate CRC-16/Modbus using the Phnix lookup tables."""
    crc_hi = 0xFF
    crc_lo = 0xFF
    for b in data:
        idx = (crc_hi ^ b) & 0xFF
        crc_hi = (crc_lo ^ CRC_TABLE_HI[idx]) & 0xFF
        crc_lo = CRC_TABLE_LO[idx]
    return ((crc_hi << 8) | (crc_lo & 0xFF)) & 0xFFFF


def build_packet(payload: bytes) -> bytes:
    """Add CRC-16 to a payload and return the complete packet."""
    crc = crc16(payload)
    return payload + struct.pack('>H', crc)


def build_set_ssid(kind_code: int, mac: bytes, ssid: str) -> bytes:
    """Build 0x83/0x05 - Set WiFi SSID command (48 bytes total)."""
    ssid_bytes = ssid.encode('utf-8')
    if len(ssid_bytes) > 32:
        raise ValueError(f"SSID too long: {len(ssid_bytes)} bytes (max 32)")

    payload = bytearray(46)
    payload[0] = 0xAA
    payload[1] = 0x5A
    payload[2] = kind_code
    payload[3] = 0x83
    payload[4] = 0x05
    payload[5:11] = mac
    payload[11] = 0x30  # max capacity marker
    payload[12] = len(ssid_bytes)
    payload[13] = 0x00  # reserved
    payload[14:14 + len(ssid_bytes)] = ssid_bytes
    # remaining bytes stay 0x00 (zero-padded)

    return build_packet(bytes(payload))


def build_set_password(kind_code: int, mac: bytes, password: str,
                       security: int = SECURITY_WPA) -> bytes:
    """Build 0x83/0x07 - Set WiFi Password command (79 bytes total)."""
    pass_bytes = password.encode('utf-8')
    if len(pass_bytes) > 63:
        raise ValueError(f"Password too long: {len(pass_bytes)} bytes (max 63)")

    payload = bytearray(77)
    payload[0] = 0xAA
    payload[1] = 0x5A
    payload[2] = kind_code
    payload[3] = 0x83
    payload[4] = 0x07
    payload[5:11] = mac
    payload[11] = 0x31  # max capacity marker
    payload[12] = len(pass_bytes)
    payload[13] = security
    payload[14:14 + len(pass_bytes)] = pass_bytes
    # remaining bytes stay 0x00

    return build_packet(bytes(payload))


def build_quit_ap(kind_code: int, mac: bytes) -> bytes:
    """Build 0x83/0xFF - Quit AP mode command (48 bytes total)."""
    payload = bytearray(46)
    payload[0] = 0xAA
    payload[1] = 0x5A
    payload[2] = kind_code
    payload[3] = 0x83
    payload[4] = 0xFF
    payload[5:11] = mac
    payload[11] = 0x33  # quit_ap marker
    payload[12] = 0x33
    payload[13] = 0x33
    payload[14] = 0x33
    # [15..45] = 0x00

    return build_packet(bytes(payload))


def build_set_name(kind_code: int, mac: bytes, name: str) -> bytes:
    """Build 0x83/0x03 - Set Machine Name command (48 bytes total)."""
    name_bytes = name.encode('utf-8')
    if len(name_bytes) > 32:
        raise ValueError(f"Name too long: {len(name_bytes)} bytes (max 32)")

    payload = bytearray(46)
    payload[0] = 0xAA
    payload[1] = 0x5A
    payload[2] = kind_code
    payload[3] = 0x83
    payload[4] = 0x03
    payload[5:11] = mac
    payload[11] = 0x00  # reserved
    payload[12] = len(name_bytes)
    payload[13] = 0x00  # reserved
    payload[14:14 + len(name_bytes)] = name_bytes

    return build_packet(bytes(payload))


def learn_device(sock: socket.socket, timeout: float = 5.0) -> tuple:
    """
    Read the first packet from the device to learn its kind_code and MAC.
    Returns (kind_code, mac_bytes).
    """
    sock.settimeout(timeout)
    data = sock.recv(4096)

    # Find first AA5A header
    idx = data.find(b'\xAA\x5A')
    if idx == -1:
        raise RuntimeError("No valid packet received from device")

    kind_code = data[idx + 2]
    mac = data[idx + 5:idx + 11]
    print(f"  Device kind_code: 0x{kind_code:02X}")
    print(f"  Device MAC: {':'.join(f'{b:02x}' for b in mac)}")
    return kind_code, mac


def setup_wifi(host: str, port: int, ssid: str, password: str,
               security: int = SECURITY_WPA, name: str = None):
    """
    Complete WiFi module setup procedure.

    1. Connect to module at host:port
    2. Learn device identity from its broadcast
    3. Send WiFi SSID
    4. Send WiFi password
    5. Optionally set machine name
    6. Send quit AP command (10x)
    """
    print(f"[1/6] Connecting to {host}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    print("  Connected!")

    print("[2/6] Learning device identity...")
    kind_code, mac = learn_device(sock)

    print(f"[3/6] Setting WiFi SSID: '{ssid}'")
    pkt = build_set_ssid(kind_code, mac, ssid)
    sock.sendall(pkt)
    print(f"  Sent {len(pkt)} bytes: {pkt.hex()}")
    time.sleep(0.5)

    print(f"[4/6] Setting WiFi password (security={security})")
    pkt = build_set_password(kind_code, mac, password, security)
    sock.sendall(pkt)
    print(f"  Sent {len(pkt)} bytes: {pkt.hex()}")
    time.sleep(0.5)

    if name:
        print(f"[5/6] Setting machine name: '{name}'")
        pkt = build_set_name(kind_code, mac, name)
        sock.sendall(pkt)
        print(f"  Sent {len(pkt)} bytes: {pkt.hex()}")
        time.sleep(0.5)
    else:
        print("[5/6] Skipping machine name (not specified)")

    # Wait for device to process and verify
    print("  Waiting 6 seconds for device to apply settings...")
    time.sleep(6)

    print("[6/6] Sending quit AP command (10x)...")
    pkt = build_quit_ap(kind_code, mac)
    for i in range(10):
        sock.sendall(pkt)
        print(f"  Sent quit_ap #{i+1}/10: {pkt.hex()}")
        time.sleep(0.1)

    print("\nDone! Module should now exit AP mode and connect to your WiFi.")
    print("You can find it on your network by scanning for port 60000.")

    sock.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Configure WiFi on Phnix/Hayward pool heat pump module",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup with default module AP address:
  python wifi_setup.py --ssid "MyHomeWifi" --password "MyPassword123"

  # Setup with custom module address and machine name:
  python wifi_setup.py --host 192.168.2.1 --ssid "MyWifi" --password "pass" --name "Pool Pump"

  # Open network (no password):
  python wifi_setup.py --ssid "OpenNetwork" --security 0

Security types:
  0 = Open (no password)
  1 = WEP-64
  2 = WEP-128
  3 = WPA/WPA2 (default)
""")
    parser.add_argument('--host', default='192.168.2.1',
                        help='Module IP address (default: 192.168.2.1)')
    parser.add_argument('--port', type=int, default=60000,
                        help='Module TCP port (default: 60000)')
    parser.add_argument('--ssid', required=True,
                        help='Home WiFi SSID to configure')
    parser.add_argument('--password', default='',
                        help='Home WiFi password')
    parser.add_argument('--security', type=int, default=SECURITY_WPA,
                        choices=[0, 1, 2, 3],
                        help='Security type: 0=Open, 1=WEP64, 2=WEP128, 3=WPA (default: 3)')
    parser.add_argument('--name', default=None,
                        help='Machine name to set (optional)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print packets without sending')

    args = parser.parse_args()

    if args.security == SECURITY_OPEN and args.password:
        print("Warning: password ignored for open network (security=0)")
        args.password = ''

    if args.dry_run:
        print("DRY RUN - showing packets that would be sent:\n")
        # Use placeholder kind_code and MAC
        kind = 0xB1
        mac = bytes([0x00, 0x2F, 0xA8, 0x00, 0x0E, 0xDC])
        print(f"Set SSID '{args.ssid}':")
        print(f"  {build_set_ssid(kind, mac, args.ssid).hex()}\n")
        print(f"Set Password (len={len(args.password)}, security={args.security}):")
        print(f"  {build_set_password(kind, mac, args.password, args.security).hex()}\n")
        if args.name:
            print(f"Set Name '{args.name}':")
            print(f"  {build_set_name(kind, mac, args.name).hex()}\n")
        print(f"Quit AP:")
        print(f"  {build_quit_ap(kind, mac).hex()}\n")
        return

    setup_wifi(
        host=args.host,
        port=args.port,
        ssid=args.ssid,
        password=args.password,
        security=args.security,
        name=args.name,
    )


if __name__ == '__main__':
    main()
