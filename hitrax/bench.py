"""Speed test for getting both mono cameras to the PC.

Runs a handful of camera setups back to back and prints one table, so we can
see which way of streaming holds 120 fps on this PC and network.

    python -m hitrax.bench

Takes about 3 minutes. The camera reboots between setups, so expect a pause
before each line.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import timedelta

import depthai as dai

from hitrax.camera_check import NATIVE_MODES, Stats, connect

NAMES = ("left", "right")
SOCKETS = (dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C)
WARMUP_S = 2.0
MEASURE_S = 6.0


@dataclass(frozen=True)
class Trial:
    label: str
    cameras: int
    size: tuple[int, int]
    fps: float
    paired: bool = False


TRIALS = [
    Trial("1 cam 640x400 @120", 1, (640, 400), 120),
    Trial("2 cam 640x400 @120", 2, (640, 400), 120),
    Trial("2 cam 640x400 @120 paired", 2, (640, 400), 120, paired=True),
    Trial("2 cam 640x400 @90", 2, (640, 400), 90),
    Trial("2 cam 640x400 @60", 2, (640, 400), 60),
    Trial("2 cam 1280x800 @30", 2, (1280, 800), 30),
]


def build(pipeline: dai.Pipeline, trial: Trial) -> list[dai.MessageQueue]:
    outs = []
    sensor_res = trial.size if trial.size in NATIVE_MODES else None
    for socket in SOCKETS[: trial.cameras]:
        cam = pipeline.create(dai.node.Camera).build(
            socket, sensorResolution=sensor_res, sensorFps=trial.fps
        )
        cam.initialControl.setManualExposure(500, 800)
        outs.append(cam.requestOutput(trial.size, type=dai.ImgFrame.Type.GRAY8, fps=trial.fps))

    queue_size = int(trial.fps)
    if not trial.paired:
        return [o.createOutputQueue(maxSize=queue_size, blocking=False) for o in outs]

    # Pair left and right on the camera so they travel as one message
    sync = pipeline.create(dai.node.Sync)
    sync.setSyncThreshold(timedelta(milliseconds=4))
    for name, out in zip(NAMES, outs):
        out.link(sync.inputs[name])
    return [sync.out.createOutputQueue(maxSize=queue_size, blocking=False)]


def measure(device: dai.Device, trial: Trial) -> tuple[list[Stats], float, float]:
    with dai.Pipeline(device) as pipeline:
        pipeline.setXLinkChunkSize(0)
        queues = build(pipeline, trial)
        pipeline.start()

        stats = [Stats() for _ in range(trial.cameras)]
        css, mss = [], []
        start = time.monotonic()
        warm = False
        next_cpu = start + WARMUP_S
        while time.monotonic() - start < WARMUP_S + MEASURE_S:
            if not warm and time.monotonic() - start >= WARMUP_S:
                stats = [Stats() for _ in range(trial.cameras)]
                warm = True
            for i, q in enumerate(queues):
                for msg in q.tryGetAll():
                    if trial.paired:
                        for j, name in enumerate(NAMES):
                            stats[j].add(msg[name])
                    else:
                        stats[i].add(msg)
            if warm and time.monotonic() >= next_cpu:
                next_cpu += 1
                css.append(device.getLeonCssCpuUsage().average * 100)
                mss.append(device.getLeonMssCpuUsage().average * 100)
            time.sleep(0.002)

    avg = lambda xs: sum(xs) / len(xs) if xs else float("nan")  # noqa: E731
    return stats, avg(css), avg(mss)


def connect_with_retry(ip: str | None, attempts: int = 8) -> dai.Device | None:
    for _ in range(attempts):
        device = connect(ip, verbose=False)
        if device is not None:
            return device
        time.sleep(3)
    return None


def print_sensor_modes(device: dai.Device) -> None:
    for feat in device.getConnectedCameraFeatures():
        if feat.socket != SOCKETS[0]:
            continue
        print(f"Left camera sensor: {feat.sensorName}")
        for c in feat.configs:
            print(f"  {c.width}x{c.height}  {c.minFps:.0f} to {c.maxFps:.0f} fps  {c.type.name}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Find which camera setup holds 120 fps.")
    p.add_argument("--ip", help="connect to this address instead of searching")
    args = p.parse_args(argv)

    header = f"{'setup':<28}{'fps L / R':>16}{'dropped L / R':>17}{'camera CPU css / mss':>23}"
    first = True
    for trial in TRIALS:
        device = connect_with_retry(args.ip)
        if device is None:
            print(f"{trial.label:<28}could not connect, camera may still be rebooting")
            continue
        with device:
            if first:
                print_sensor_modes(device)
                print()
                print(header)
                first = False
            try:
                stats, css, mss = measure(device, trial)
            except Exception as e:  # keep going so one bad setup doesn't hide the rest
                print(f"{trial.label:<28}failed: {e}")
                continue
        fps = " / ".join(f"{s.fps:5.1f}" for s in stats)
        dropped = " / ".join(f"{s.dropped:4d}" for s in stats)
        print(f"{trial.label:<28}{fps:>16}{dropped:>17}{css:>14.0f}% / {mss:3.0f}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
