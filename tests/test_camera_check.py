import datetime

import pytest

dai = pytest.importorskip("depthai")
np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from hitrax.camera_check import Stats  # noqa: E402


def make_frame(seq, t, brightness):
    f = dai.ImgFrame()
    f.setSequenceNum(seq)
    f.setTimestampDevice(datetime.timedelta(seconds=t))
    f.setWidth(4)
    f.setHeight(2)
    f.setType(dai.ImgFrame.Type.GRAY8)
    f.setData(np.full(8, brightness, dtype=np.uint8))
    return f


def test_fps_and_steady_light():
    s = Stats()
    for i in range(121):
        s.add(make_frame(i, i / 120, 100))
    assert s.fps == pytest.approx(120)
    assert s.dropped == 0
    assert s.light_variation_pct == 0


def test_counts_dropped_frames():
    s = Stats()
    for seq in (0, 1, 4, 5, 9):
        s.add(make_frame(seq, seq / 120, 100))
    assert s.dropped == 5


def test_flicker_shows_as_light_variation():
    s = Stats()
    for i in range(60):
        s.add(make_frame(i, i / 120, 100 if i % 2 else 80))
    assert s.light_variation_pct > 15


def test_sensor_fps_counts_frames_that_never_arrived():
    s = Stats()
    # camera shoots 120 fps but only every third frame makes it to the PC
    for seq in range(0, 121, 3):
        s.add(make_frame(seq, seq / 120, 100))
    assert s.fps == pytest.approx(40)
    assert s.sensor_fps == pytest.approx(120)
