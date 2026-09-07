import cv2
import time
import sys

OUT_FILE = 'webcam_record.mp4'
DURATION = 10.0  # seconds
FPS = 10.0

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print('ERROR: cannot open webcam (index 0)')
    sys.exit(1)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(OUT_FILE, fourcc, FPS, (width, height))

print(f'Recording {DURATION}s from webcam to {OUT_FILE} at {FPS} FPS ({width}x{height})')
start = time.time()
frames = 0
try:
    while time.time() - start < DURATION:
        ret, frame = cap.read()
        if not ret:
            print('Frame capture failed, stopping')
            break
        out.write(frame)
        frames += 1
finally:
    cap.release()
    out.release()

print(f'Done — saved {frames} frames to {OUT_FILE}')
