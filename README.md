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
| Gigabit 802.3af PoE injector, like the TP-Link TL-POE150S | Powers the camera. Must be gigabit (10/100 ones are too slow) and 802.3af, not passive PoE. Rated 32 to 104°F, so keep it indoors if the garage gets extreme. |
| M12 X-coded 8 pin to RJ45 cable | The camera has a round industrial connector, not a normal network jack. |
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

## Getting started on a Windows PC

Use **VS Code**, not Visual Studio. They share a name, but Visual Studio is the
big one built for C# and C++. VS Code is free, lighter, and what most Python
work is done in.

### One time setup

1. You need **Python 3.11 or newer**. Run `py -0` in a terminal to see what you have. If nothing
   3.11 or newer shows up, install **Python 3.12** from python.org and check **Add python.exe to PATH**
   on the first installer screen.
2. Install **VS Code** and **Git for Windows**.
3. In VS Code, open the Extensions panel, search **Python**, and install the one by Microsoft.
4. Open a terminal in VS Code (**Terminal > New Terminal**) and get the code:
   ```
   git clone -b claude/diy-hitrax-golf-monitor-eono6w https://github.com/zillerw-cpu/DIY-Hitrax.git
   ```
5. **File > Open Folder** and pick the `DIY-Hitrax` folder.
6. In a new terminal, set up a Python environment and install everything. Run these one
   at a time, and if `py -0` showed a different version like 3.13, use that number instead of 3.12:
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install -e ".[dev]"
   ```
   If `activate` says running scripts is disabled, run this once and try again:
   ```
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

### Step 1: make sure the code works (no camera needed)

```
pytest
python -m hitrax.calc 95 28 -15
```

Tests should all pass, and the calculator prints carry, apex and hang time.

### Step 2: hook up the camera

Plugging straight into the PC is the best setup. The camera gets the whole
gigabit link to itself.

1. Camera to the **PoE out** port on the injector.
2. Injector **data in** port to the PC's Ethernet port.
3. Give it about a minute. With no router handing out addresses, the camera
   falls back to `169.254.1.222` and Windows picks its own address in the same range.
4. Check the link is actually gigabit: **Settings > Network & internet > Ethernet**,
   look at **Link speed**. It should say 1000/1000. If it says 100/100, swap the
   patch cable for a Cat5e or Cat6 one.

The PC's internet will go over WiFi while the Ethernet port is used by the camera.

If the camera check can't find the camera, give the PC a fixed address on that port:
**Settings > Network & internet > Ethernet > IP assignment > Edit > Manual**, turn on
IPv4, IP address `169.254.1.10`, subnet mask `255.255.0.0` (or prefix length `16`),
leave gateway and DNS blank.

### Step 3: camera check

```
python -m hitrax.camera_check
```

Allow Python through the Windows firewall when it asks, and check both
**Private** and **Public**, since a direct cable shows up as a public network. You should see both
mono cameras side by side. What you want:

| On screen | Good | If not |
|---|---|---|
| fps | close to 120 on both | check link speed says 1000 |
| dropped | stays at 0 | same as above |
| light variation | under 5% with nothing moving in view | your lights likely flicker, try other lights |
| ball tossed through the view | round, not a streak | press `[` for shorter exposure, `=` for more ISO if it gets dark |

Press `s` to save a snapshot of both cameras to `captures/`, `q` to quit.

## Status

* [x] Flight model with tests
* [x] Config with feature toggles
* [x] Distance calculator (`python -m hitrax.calc`)
* [x] Camera check with fps, dropped frames, flicker and exposure tuning
* [ ] Crop to the ball flight band
* [ ] Contact detection at the tee
* [ ] Ball detection and stereo triangulation
* [ ] Calibration routine for the garage layout
* [ ] Web display and session log
* [ ] Swing tracking (experimental)
