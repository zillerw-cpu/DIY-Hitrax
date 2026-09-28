"""First hardware test for the OAK.

Confirms the camera is found, runs both mono cameras at 120 fps, and lets you
dial in exposure so a ball in flight looks sharp instead of a streak.

    python -m hitrax.camera_check

Keys:
    [ ]   exposure shorter / longer
    - =   ISO down / up
    s     save a snapshot of both cameras to captures/
    q     quit

What to look for:
    * fps close to 120 on both cameras with dropped staying at 0
    * light variation under about 5%, higher usually means the lights flicker
    * a ball tossed through the view looks round, not smeared
"""

from __future__ import annotations

import argparse
import collections
import time
from pathlib import Path

import cv2
import depthai as dai

CAPTURE_DIR = Path("captures")
MIN_EXPOSURE_US, MAX_EXPOSURE_US = 20, 8000
MIN_ISO, MAX_ISO = 100, 1600
# 80 mph in mm per microsecond, used to show how much a ball smears
BALL_MM_PER_US = 80 * 0.44704 / 1000

NO_DEVICE_HELP = """
No OAK camera found. Things to check:
  1. The PoE injector or switch port is powering the camera
  2. The camera and this computer are on the same network
  3. Windows firewall is allowing Python (it pops up a prompt the first time)
  4. Give it 20 to 30 seconds after plugging in, the camera takes a bit to boot
"""


class Stats:
    """Rolling fps, dropped frames and brightness for one camera."""

    def __init__(self, window: int = 240):
        self.times: collections.deque[float] = collections.deque(maxlen=window)
        self.brightness: collections.deque[float] = collections.deque(maxlen=window)
        self.last_seq: int | None = None
        self.dropped = 0

    def add(self, frame: dai.ImgFrame) -> None:
        seq = frame.getSequenceNum()
        if self.last_seq is not None and seq > self.last_seq + 1:
            self.dropped += seq - self.last_seq - 1
        self.last_seq = seq
        self.times.append(frame.getTimestampDevice().total_seconds())
        self.brightness.append(float(frame.getFrame().mean()))

    @property
    def fps(self) -> float:
        if len(self.times) < 2 or self.times[-1] == self.times[0]:
            return 0.0
        return (len(self.times) - 1) / (self.times[-1] - self.times[0])

    @property
    def light_variation_pct(self) -> float:
        if not self.brightness:
            return 0.0
        mean = sum(self.brightness) / len(self.brightness)
        if mean == 0:
            return 0.0
        return (max(self.brightness) - min(self.brightness)) / mean * 100


def overlay(img, name: str, stats: Stats, target_fps: float):
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    ok, warn = (80, 220, 80), (0, 180, 255)
    fps_color = ok if stats.fps >= 0.9 * target_fps and stats.dropped == 0 else warn
    light_color = ok if stats.light_variation_pct < 5 else warn
    cv2.putText(img, f"{name}  {stats.fps:5.1f} fps  dropped {stats.dropped}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, fps_color, 2)
    cv2.putText(img, f"light variation {stats.light_variation_pct:4.1f}%",
                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, light_color, 2)
    return img


def send_exposure(controls, exposure_us: int, iso: int) -> None:
    for q in controls:
        ctrl = dai.CameraControl()
        ctrl.setManualExposure(exposure_us, iso)
        q.send(ctrl)


def run(width: int, height: int, fps: float, exposure_us: int, iso: int) -> int:
    devices = dai.Device.getAllAvailableDevices()
    if not devices:
        print(NO_DEVICE_HELP)
        return 1
    for d in devices:
        print(f"Found {d.name} ({d.getDeviceId()}) over {d.protocol.name}")

    with dai.Pipeline() as pipeline:
        queues, controls = [], []
        for socket in (dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C):
            cam = pipeline.create(dai.node.Camera).build(socket, sensorFps=fps)
            cam.initialControl.setManualExposure(exposure_us, iso)
            out = cam.requestOutput((width, height), type=dai.ImgFrame.Type.GRAY8, fps=fps)
            queues.append(out.createOutputQueue(maxSize=int(fps), blocking=False))
            controls.append(cam.inputControl.createInputQueue())

        pipeline.start()
        stats = [Stats(), Stats()]
        latest = [None, None]
        CAPTURE_DIR.mkdir(exist_ok=True)

        while pipeline.isRunning():
            # Drain everything so fps and dropped reflect the camera, not
            # how fast the preview window redraws.
            for i, q in enumerate(queues):
                for frame in q.tryGetAll():
                    stats[i].add(frame)
                    latest[i] = frame

            if all(f is not None for f in latest):
                left = overlay(latest[0].getFrame(), "LEFT", stats[0], fps)
                right = overlay(latest[1].getFrame(), "RIGHT", stats[1], fps)
                view = cv2.hconcat([left, right])
                blur_mm = exposure_us * BALL_MM_PER_US
                cv2.putText(
                    view,
                    f"exposure {exposure_us} us  ISO {iso}  blur at 80 mph {blur_mm:.0f} mm"
                    "   [ ] exposure  - = ISO  s save  q quit",
                    (10, view.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                )
                cv2.imshow("OAK camera check", view)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key in (ord("["), ord("]")):
                factor = 0.5 if key == ord("[") else 2
                exposure_us = int(min(MAX_EXPOSURE_US, max(MIN_EXPOSURE_US, exposure_us * factor)))
                send_exposure(controls, exposure_us, iso)
            elif key in (ord("-"), ord("=")):
                factor = 0.5 if key == ord("-") else 2
                iso = int(min(MAX_ISO, max(MIN_ISO, iso * factor)))
                send_exposure(controls, exposure_us, iso)
            elif key == ord("s") and all(f is not None for f in latest):
                stamp = time.strftime("%Y%m%d_%H%M%S")
                for name, f in zip(("left", "right"), latest):
                    path = CAPTURE_DIR / f"{stamp}_{name}.png"
                    cv2.imwrite(str(path), f.getFrame())
                    print(f"saved {path}")

    cv2.destroyAllWindows()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check the OAK mono cameras and exposure.")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=400)
    p.add_argument("--fps", type=float, default=120)
    p.add_argument("--exposure-us", type=int, default=500)
    p.add_argument("--iso", type=int, default=800)
    args = p.parse_args(argv)
    return run(args.width, args.height, args.fps, args.exposure_us, args.iso)


if __name__ == "__main__":
    raise SystemExit(main())
