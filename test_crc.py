"""Verify CRC and show example packets."""
import sys
sys.path.insert(0, '.')
from wifi_setup import crc16, build_set_ssid, build_set_password, build_quit_ap

# Verify CRC against known packet from capture.bin
known_payload = bytes.fromhex('aa5ab18001002fa8000edc010106787979824c825a824c3d3d0002000000000000')
crc = crc16(known_payload)
print(f'CRC of known status packet: 0x{crc:04X} (expected: 0xBA7E)')
print(f'Match: {crc == 0xBA7E}')
print()

kind = 0xB1
mac = bytes.fromhex('002fa8000edc')

print('Set SSID "Fabulousliving":')
pkt = build_set_ssid(kind, mac, 'Fabulousliving')
print(f'  {pkt.hex()}')
print(f'  Length: {len(pkt)} bytes')
print()

print('Set Password "cillaisafreeloader!" (WPA):')
pkt = build_set_password(kind, mac, 'cillaisafreeloader!', 3)
print(f'  {pkt.hex()}')
print(f'  Length: {len(pkt)} bytes')
print()

print('Quit AP:')
pkt = build_quit_ap(kind, mac)
print(f'  {pkt.hex()}')
print(f'  Length: {len(pkt)} bytes')
