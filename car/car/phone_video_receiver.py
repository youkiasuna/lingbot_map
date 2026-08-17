import argparse

import cv2


def main() -> None:
    parser = argparse.ArgumentParser(description="Read a phone or IP-camera MJPEG stream")
    parser.add_argument("--url", default="http://192.168.4.2:8080/video", help="MJPEG stream URL")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.url)
    if not cap.isOpened():
        raise SystemExit(f"Unable to open stream: {args.url}")

    print(f"Streaming from {args.url}")
    print("Press 'q' to quit")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        cv2.imshow("Phone Stream", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
