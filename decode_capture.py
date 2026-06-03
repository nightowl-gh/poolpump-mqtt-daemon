"""Decode the live capture.bin from port 60000."""

data = open('capture.bin', 'rb').read()

def decode_temp(b):
    return (b - 60) / 2.0

# Parse all messages
messages = []
i = 0
while i < len(data) - 4:
    if data[i] == 0xAA and data[i+1] == 0x5A:
        # Find next AA5A
        next_aa = len(data)
        for j in range(i+2, min(i+100, len(data)-1)):
            if data[j] == 0xAA and data[j+1] == 0x5A:
                next_aa = j
                break
        pkt_len = next_aa - i
        if pkt_len > 79:
            pkt_len = 79
        messages.append((i, data[i:i+pkt_len]))
        i += pkt_len
    else:
        i += 1

# Count message types
from collections import Counter
type_counts = Counter()
for offset, msg in messages:
    if len(msg) >= 5:
        key = (msg[3], msg[4])
        type_counts[key] += 1

print(f"File size: {len(data)} bytes")
print(f"Total messages: {len(messages)}")
print()
print("Message type distribution:")
for (cmd, sub), count in sorted(type_counts.items()):
    print(f"  cmd=0x{cmd:02x} sub=0x{sub:02x}: {count} messages")

# Show one complete cycle
print()
print("=" * 60)
print("ONE COMPLETE BROADCAST CYCLE:")
print("=" * 60)

cycle_seen = set()
for offset, msg in messages:
    if len(msg) < 5:
        continue
    cmd = msg[3]
    sub = msg[4]
    key = (cmd, sub)
    if key in cycle_seen and key == (0x80, 0x01):
        break
    cycle_seen.add(key)

    if cmd == 0x80 and sub == 0x01 and len(msg) >= 35:
        power = "ON" if msg[11] == 1 else "OFF"
        modes = {0:'Cool',1:'Heat',2:'Auto'}
        mode = modes.get(msg[12], f"0x{msg[12]:02x}")
        print(f"  Status (0x80/01): Power={power}, Mode={mode}, HeatSet={decode_temp(msg[15])}C, CoolSet={decode_temp(msg[14])}C")
    elif cmd == 0xD0 and sub == 0x01 and len(msg) >= 31:
        print(f"  Realtime (0xD0/01): Inlet={decode_temp(msg[12])}C, Outlet={decode_temp(msg[13])}C, Ambient={decode_temp(msg[14])}C")
    elif cmd == 0xD0 and sub == 0x00 and len(msg) >= 15:
        dtype = msg[11]
        names = {0x23:'Outlet Hist', 0x24:'Inlet Hist', 0x4F:'DevStatus', 0x53:'Status S', 0x54:'Status T'}
        print(f"  Data (0xD0/00) [{names.get(dtype, f'0x{dtype:02x}')}]: count={msg[12]} page={msg[13]}")
    elif cmd == 0x80 and sub == 0x00 and len(msg) >= 15:
        group = msg[11]
        gn = {0x21:'Timer', 0x44:'D', 0x45:'E', 0x46:'F', 0x48:'H', 0x50:'P', 0x52:'R'}
        print(f"  Factory (0x80/00) [{gn.get(group, f'0x{group:02x}')}]")
    elif cmd == 0x80 and sub == 0x02:
        print(f"  Info (0x80/02): {msg[11:30].hex()}")
    elif cmd == 0x80 and sub == 0x03:
        name_data = msg[14:46] if len(msg) >= 46 else msg[14:]
        name = bytes(b for b in name_data if b != 0).decode('utf-8', errors='replace')
        print(f'  Name (0x80/03): "{name}"')
    elif cmd == 0x80 and sub == 0x04:
        print(f"  Barcode (0x80/04): valid={msg[11]}")
    elif cmd == 0x80 and sub == 0x05:
        ssid_len = msg[12]
        ssid = msg[14:14+ssid_len].decode('ascii', errors='replace') if len(msg) > 14+ssid_len else '?'
        print(f'  WiFi SSID (0x80/05): "{ssid}"')
    elif cmd == 0x80 and sub == 0x06:
        print(f"  WiFi Info (0x80/06): {msg[11:25].hex()}")
    elif cmd == 0x80 and sub == 0x07:
        pass_len = msg[12]
        print(f"  WiFi Pass (0x80/07): len={pass_len}")
    elif cmd == 0xD0 and sub == 0x02:
        print(f"  TimeSync? (0xD0/02): {msg[11:25].hex()}")
    else:
        print(f"  Pkt (0x{cmd:02x}/0x{sub:02x}): {msg[11:20].hex() if len(msg) > 20 else msg.hex()}")

# Current readings
print()
print("=" * 60)
print("CURRENT READINGS (latest values):")
print("=" * 60)

# Get latest status and realtime
for offset, msg in reversed(messages):
    if len(msg) >= 35 and msg[3] == 0x80 and msg[4] == 0x01:
        power = "ON" if msg[11] == 1 else "OFF"
        modes = {0:'Cool',1:'Heat',2:'Auto',3:'Rapid Heat'}
        mode = modes.get(msg[12], f"0x{msg[12]:02x}")
        ms = f"0x{msg[13]:02x}"
        print(f"  Power: {power}")
        print(f"  Mode: {mode} (select={ms})")
        print(f"  Heat Set: {decode_temp(msg[15])}C")
        print(f"  Cool Set: {decode_temp(msg[14])}C")
        print(f"  Auto Set: {decode_temp(msg[16])}C")
        print(f"  Heat Range: {decode_temp(msg[20])}~{decode_temp(msg[19])}C")
        print(f"  Cool Range: {decode_temp(msg[18])}~{decode_temp(msg[17])}C")
        print(f"  Auto Range: {decode_temp(msg[22])}~{decode_temp(msg[21])}C")
        print(f"  Hot Water: {decode_temp(msg[30])}C ({decode_temp(msg[32])}~{decode_temp(msg[31])})")
        sb1 = msg[25]
        sb2 = msg[26]
        sb2_bits = [(sb2 >> j) & 1 for j in range(8)]
        print(f"  Silent Timer: {'ON' if sb2_bits[0] else 'OFF'}")
        print(f"  Fan: {'ON' if sb2_bits[4] else 'OFF'}")
        print(f"  Water Pump: {'ON' if sb2_bits[5] else 'OFF'}")
        break

print()
for offset, msg in reversed(messages):
    if len(msg) >= 31 and msg[3] == 0xD0 and msg[4] == 0x01:
        print(f"  Inlet Temp: {decode_temp(msg[12])}C")
        print(f"  Outlet Temp: {decode_temp(msg[13])}C")
        print(f"  Ambient Temp: {decode_temp(msg[14])}C")
        print(f"  Defrost: 0x{msg[11]:02x}")
        if len(msg) > 20:
            print(f"  Fault Code: 0x{msg[20]:02x}")
            if msg[20] != 0:
                fault = bytes(msg[21:25])
                print(f"  Fault Msg: {fault}")
        break
