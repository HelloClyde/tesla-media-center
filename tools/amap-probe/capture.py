"""Capture only the local probe app; raw records remain under .local-data.

Requires matching Frida 16.x Python/server versions (Java bridge bundled).
Start the probe app, attach this script, then press the route-test button.
"""
import argparse
import json
import time
from pathlib import Path
import frida

parser = argparse.ArgumentParser()
parser.add_argument('--device', required=True, help='Explicit Frida device ID')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
folder = root / '.local-data/amap-sdk/captures' / time.strftime('%Y%m%d-%H%M%S')
folder.mkdir(parents=True, mode=0o700)
device = frida.get_device(args.device, timeout=10)
process = device.get_process('com.helloclyde.amapprobe')
session = device.attach(process.pid)
counter = 0


def on_message(message, data):
    global counter
    counter += 1
    record = folder / f'{counter:06d}.json'
    record.write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding='utf-8')
    record.chmod(0o600)
    if data is not None:
        binary = folder / f'{counter:06d}.bin'
        binary.write_bytes(data)
        binary.chmod(0o600)
    # No URLs, headers or raw exceptions on the console: they may contain keys.
    print('Captured', counter, message.get('payload', {}).get('kind', message['type']), flush=True)


script = session.create_script(Path(__file__).with_name('capture.js').read_text(encoding='utf-8'))
script.on('message', on_message)
script.load()
print('Capturing the probe app. Press Enter to stop. Private output:', folder)
try:
    input()
finally:
    script.unload()
    session.detach()
