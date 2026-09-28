# DIY HitTrax

A garage batting tracker for hitting off a tee into a net. An OAK-D S2 PoE
camera watches the ball come off the bat, and the software works out exit
velo, launch angle and spray direction, then projects where the ball would
have landed on a real field.

## Hardware

| Part | Why |
|---|---|
| OAK-D S2 PoE | Two global shutter mono cameras at 120 fps for tracking the ball. Color camera is only used for the optional swing feature. |
| Raspberry Pi 5, 8GB, with active cooler | Always on box in the garage that runs the tracker. A laptop works too. |
| PoE injector or PoE switch | Powers the camera. The Pi can't. |
| NVMe hat and drive (optional) | Only needed if you want to save swing video. |

## How it works

1. Stream both mono cameras, cropped to the band the ball flies through, so it fits in 1 Gbps.
2. Keep the last couple seconds of frames in memory and watch a small box around the tee.
3. When the ball leaves the tee, find it in both views and triangulate its 3D position frame by frame.
4. Fit the path to get exit velo, launch angle and spray angle.
5. Run the flight model (`hitrax/flight.py`) to estimate carry, apex and hang time.
6. Show results on a web page you can pull up on a phone, tablet or TV, and log every swing.

## What to expect for accuracy

| Number | How good |
|---|---|
| Exit velo | Should be solid with the camera off to the side of the hitting lane |
| Launch angle | Same |
| Spray direction | Roughest number. The stereo baseline is only 7.5 cm, so depth gets noisy. |
| Distance | Estimated with a physics model, not measured. Spin is guessed from launch angle. HitTrax works the same way indoors. |

## Features you can toggle

In `config.toml`:

* `swing_tracking`: experimental. Body pose on the color camera plus swing clips. Off by default since it shares bandwidth with ball tracking.

## Status

* [x] Flight model with tests
* [x] Config with feature toggles
* [ ] Camera capture and cropping
* [ ] Contact detection at the tee
* [ ] Ball detection and stereo triangulation
* [ ] Calibration routine for the garage layout
* [ ] Web display and session log
* [ ] Swing tracking (experimental)

## Running tests

```
pip install -e ".[dev]"
pytest
```
