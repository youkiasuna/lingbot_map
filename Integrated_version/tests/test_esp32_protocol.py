import unittest
from unittest.mock import Mock, patch

from Integrated_version.hardware.esp32_protocol import COMMAND_MAP, send_command


class Esp32ProtocolTests(unittest.TestCase):
    def test_motion_map_matches_firmware_commands(self):
        self.assertEqual(
            COMMAND_MAP,
            {"forward": "F", "backward": "B", "left": "L", "right": "R", "stop": "S"},
        )

    def test_sends_newline_terminated_command_and_returns_reply(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.recv.return_value = b"OK\r\n"

        with patch("Integrated_version.hardware.esp32_protocol.socket.create_connection", return_value=connection) as connect:
            reply = send_command("127.0.0.1", 8888, "F")

        connect.assert_called_once_with(("127.0.0.1", 8888), timeout=2)
        connection.sendall.assert_called_once_with(b"F\n")
        self.assertEqual(reply, "OK")


if __name__ == "__main__":
    unittest.main()
