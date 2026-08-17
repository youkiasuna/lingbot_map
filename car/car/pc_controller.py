import argparse
import socket
import sys

COMMAND_MAP = {
    "forward": "F",
    "backward": "B",
    "left": "L",
    "right": "R",
    "stop": "S",
}


def send_command(ip: str, port: int, command: str) -> None:
    payload = command.encode("utf-8") + b"\n"
    with socket.create_connection((ip, port), timeout=2) as sock:
        sock.sendall(payload)
        response = sock.recv(1024).decode("utf-8", errors="ignore").strip()
        print(f"ESP32 response: {response}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send motion commands to the ESP32 car controller")
    parser.add_argument("--ip", default="192.168.4.1", help="ESP32 IP address")
    parser.add_argument("--port", type=int, default=8888, help="ESP32 TCP port")
    parser.add_argument("--command", choices=sorted(COMMAND_MAP.keys()), help="One-shot command")
    args = parser.parse_args()

    if args.command:
        send_command(args.ip, args.port, COMMAND_MAP[args.command])
    else:
        print("No command specified. Use --command forward|backward|left|right|stop")
        sys.exit(1)
