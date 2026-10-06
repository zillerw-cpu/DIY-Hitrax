"""First hardware test for the OAK.

Confirms the camera is found, runs both mono cameras at 120 fps, and lets you
dial in exposure so a ball in flight looks sharp instead of a streak.

    python -m hitrax.camera_check

Keys:
    [ ]   exposure shorter / longer
    - =   ISO down / up
    s     save a snapshot of both cameras to captures/
    q     quit

Numbers also print to the terminal every 2 seconds. Add --no-preview to skip
the window, or --cameras 1 to run just the left camera.

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

# Where the camera puts itself when there's no router handing out addresses,
# which is the case when it's plugged straight into the PC.
FALLBACK_IP = "169.254.1.222"

# Sizes the mono sensors can output directly, no resizing needed
NATIVE_MODES = {(1280, 800), (1280, 720), (640, 400)}

NO_DEVICE_HELP = """
No OAK camera found. Things to check:
  1. The PWR light on the injector is on
  2. Give it a minute after plugging in, the camera takes a bit to boot
  3. Windows firewall is allowing Python, on Public networks too
  4. Plugged straight into the PC? Set the PC's Ethernet adapter to a fixed
     IP of 169.254.1.10 with subnet mask 255.255.0.0, then try again
  5. Going through a router instead? Find the camera in the router's device
     list and run: python -m hitrax.camera_check --ip <that address>
"""


class Stats:
    """Rolling fps, dropped frames and brightness for one camera."""

    def __init__(self, window: int = 240):
        self.times: collections.deque[float] = collections.deque(maxlen=window)
        self.seqs: collections.deque[int] = collections.deque(maxlen=window)
        self.brightness: collections.deque[float] = collections.deque(maxlen=window)
        self.last_seq: int | None = None
        self.dropped = 0

    def add(self, frame: dai.ImgFrame) -> None:
        seq = frame.getSequenceNum()
        if self.last_seq is not None and seq > self.last_seq + 1:
            self.dropped += seq - self.last_seq - 1
        self.last_seq = seq
        self.times.append(frame.getTimestampDevice().total_seconds())
        self.seqs.append(seq)
        self.brightness.append(float(frame.getFrame().mean()))

    @property
    def fps(self) -> float:
        if len(self.times) < 2 or self.times[-1] == self.times[0]:
            return 0.0
        return (len(self.times) - 1) / (self.times[-1] - self.times[0])

    @property
    def sensor_fps(self) -> float:
        """How fast the camera is actually shooting, counting frames that never arrived."""
        if len(self.times) < 2 or self.times[-1] == self.times[0]:
            return 0.0
        return (self.seqs[-1] - self.seqs[0]) / (self.times[-1] - self.times[0])

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


def connect(
    ip: str | None, verbose: bool = True, config: dai.Device.Config | None = None
) -> dai.Device | None:
    """Find the camera by search, or by IP when search comes up empty.

    Windows sometimes blocks the search broadcast on a direct cable, but
    connecting by address still works.
    """
    say = print if verbose else (lambda *a: None)

    def open_device(info: dai.DeviceInfo) -> dai.Device:
        return dai.Device(info) if config is None else dai.Device(config, info)

    if ip is None:
        devices = dai.Device.getAllAvailableDevices()
        for d in devices:
            say(f"Found {d.name} ({d.getDeviceId()}) over {d.protocol.name}")
        if devices:
            return open_device(devices[0])
        ip = FALLBACK_IP
        say(f"Search found nothing, trying the direct connect address {ip}")
    else:
        say(f"Connecting to {ip}")
    try:
        return open_device(dai.DeviceInfo(ip))
    except RuntimeError:
        return None


def run(
    width: int,
    height: int,
    fps: float,
    exposure_us: int,
    iso: int,
    ip: str | None = None,
    cameras: int = 2,
    preview: bool = True,
) -> int:
    device = connect(ip)
    if device is None:
        print(NO_DEVICE_HELP)
        return 1

    names = ("LEFT", "RIGHT")[:cameras]
    sockets = (dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C)[:cameras]
    # Asking the sensor for the exact size we want avoids a resize step on the
    # camera, which can't keep up at 120 fps.
    sensor_res = (width, height) if (width, height) in NATIVE_MODES else None

    with device, dai.Pipeline(device) as pipeline:
        # Send each frame as one packet instead of 64 KB pieces, faster over PoE.
        pipeline.setXLinkChunkSize(0)
        queues, controls = [], []
        for socket in sockets:
            cam = pipeline.create(dai.node.Camera).build(
                socket, sensorResolution=sensor_res, sensorFps=fps
            )
            cam.initialControl.setManualExposure(exposure_us, iso)
            out = cam.requestOutput((width, height), type=dai.ImgFrame.Type.GRAY8, fps=fps)
            queues.append(out.createOutputQueue(maxSize=int(fps), blocking=False))
            controls.append(cam.inputControl.createInputQueue())

        pipeline.start()
        stats = [Stats() for _ in names]
        latest = [None for _ in names]
        CAPTURE_DIR.mkdir(exist_ok=True)
        next_print = time.monotonic() + 2
        if not preview:
            print("Running without a preview window, press Ctrl+C to stop")

        try:
            while pipeline.isRunning():
                # Drain everything so fps and dropped reflect the camera, not
                # how fast the preview window redraws.
                for i, q in enumerate(queues):
                    for frame in q.tryGetAll():
                        stats[i].add(frame)
                        latest[i] = frame

                if time.monotonic() >= next_print:
                    next_print += 2
                    print("   ".join(
                        f"{n} {s.fps:5.1f} fps dropped {s.dropped} light {s.light_variation_pct:4.1f}%"
                        for n, s in zip(names, stats)
                    ))

                if not preview:
                    time.sleep(0.002)
                    continue

                if all(f is not None for f in latest):
                    view = cv2.hconcat([
                        overlay(f.getFrame(), n, s, fps)
                        for f, n, s in zip(latest, names, stats)
                    ])
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
                    for n, f in zip(names, latest):
                        path = CAPTURE_DIR / f"{stamp}_{n.lower()}.png"
                        cv2.imwrite(str(path), f.getFrame())
                        print(f"saved {path}")
        except KeyboardInterrupt:
            pass

    cv2.destroyAllWindows()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check the OAK mono cameras and exposure.")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=400)
    p.add_argument("--fps", type=float, default=120)
    p.add_argument("--exposure-us", type=int, default=500)
    p.add_argument("--iso", type=int, default=800)
    p.add_argument("--ip", help=f"connect to this address instead of searching, like {FALLBACK_IP}")
    p.add_argument("--cameras", type=int, choices=(1, 2), default=2,
                   help="1 runs only the left camera, handy for finding speed limits")
    p.add_argument("--no-preview", action="store_true",
                   help="skip the window and just print numbers")
    args = p.parse_args(argv)
    return run(
        args.width, args.height, args.fps, args.exposure_us, args.iso, args.ip,
        cameras=args.cameras, preview=not args.no_preview,
    )


if __name__ == "__main__":
    raise SystemExit(main())
