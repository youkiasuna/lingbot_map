# Car control demo

This folder contains a minimal starter setup for a Wi-Fi controlled car.

## Files

- esp32_motor_control.ino: Arduino sketch for ESP32 + L298N motor control
- pc_controller.py: Python client to send motion commands to the ESP32
- web_controller.py: Browser-based controller with arrow buttons and keyboard support
- phone_video_receiver.py: Read a phone/IP-camera MJPEG stream on the computer

## Quick start

1. Upload esp32_motor_control.ino to the ESP32 with the Arduino IDE.
2. Connect your laptop and phone to the ESP32 access point named CarAP.
3. Run the controller from the computer:

```bash
python car/pc_controller.py --command forward
```

Or start the browser controller and open the page in your browser:

```bash
python car/web_controller.py --ip 192.168.4.1 --port 8000
```

Then visit `http://127.0.0.1:8000`.

4. Start the video receiver using a stream URL from your phone app (for example IP Webcam or DroidCam):

```bash
python car/phone_video_receiver.py --url http://192.168.4.2:8080/video
```

## Commands

The ESP32 accepts these single-letter commands:

- F: move forward
- B: move backward
- L: turn left
- R: turn right
- S: stop

The browser controller supports:

- Up arrow or the ▲ button: forward
- Down arrow or the ▼ button: backward
- Left arrow or the ◀ button: left
- Right arrow or the ▶ button: right
- Space or the STOP button: stop
