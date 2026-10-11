import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Integrated_version.hardware.esp32_protocol import COMMAND_MAP, send_command


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send motion commands to the ESP32 car controller")
    parser.add_argument("--ip", default="192.168.4.1", help="ESP32 IP address")
    parser.add_argument("--port", type=int, default=8888, help="ESP32 TCP port")
    parser.add_argument("--command", choices=sorted(COMMAND_MAP.keys()), help="One-shot command")
    args = parser.parse_args()

    if args.command:
        response = send_command(args.ip, args.port, COMMAND_MAP[args.command])
        print(f"ESP32 response: {response}")
    else:
        print("No command specified. Use --command forward|backward|left|right|stop")
        sys.exit(1)
