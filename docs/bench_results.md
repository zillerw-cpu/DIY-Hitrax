# Camera streaming bench results

Results from `python -m hitrax.bench` on real hardware, kept here so we know
why the streaming setup ended up the way it did.

## Round 1, 2026-10-04

Setup: OAK-D S2 PoE straight into a Windows PC (Intel 82579LM, 1000/1000
link) through a TP-Link POE150S injector. Python 3.12, depthai 3.10.
Network bootloader 0.0.26.

Sensor modes reported by the left camera (OV9282):

| Mode | fps range |
|---|---|
| 1280x800 | 2 to 130 |
| 1280x720 | 2 to 143 |
| 640x400 | 2 to 256 |

| Setup | fps L / R | dropped L / R | camera CPU css / mss |
|---|---|---|---|
| 1 cam 640x400 @120 | 110.3 | 61 | 98% / 13% |
| 2 cam 640x400 @120 | 39.8 / 40.1 | 482 / 478 | 100% / 12% |
| 2 cam 640x400 @120 paired | 24.0 / 24.0 | 569 / 569 | 99% / 13% |
| 2 cam 640x400 @90 | 44.8 / 44.4 | 270 / 275 | 100% / 12% |
| 2 cam 640x400 @60 | 53.1 / 53.1 | 44 / 43 | 100% / 14% |
| 2 cam 1280x800 @30 | 30.0 / 30.0 | 0 / 0 | 90% / 14% |

What it tells us:

* The sensor isn't the limit. 640x400 goes up to 256 fps.
* Bandwidth isn't the limit. 1280x800 at 30 fps moves about 490 Mbps with no drops.
* The camera's network processor (css) is the limit. It sits at 100% in
  every 640x400 run and tops out around 100 to 110 frames a second total,
  no matter how they're split between cameras. Each frame sent has a big
  fixed cost on that processor.
* Pairing left and right with a Sync node made it worse, because the pairing
  also ran on css.
* The other processor (mss) is mostly idle at 12 to 14%.

## Round 2 (pending)

Tries to make each frame cheaper for css to send: jumbo network packets,
Nagle on, and running the pairing on mss instead.

Jumbo packets need the PC side turned on too, otherwise the camera falls back
to normal size packets:

1. Device Manager, then Network adapters.
2. Right click **Intel(R) 82579LM Gigabit Network Connection**, Properties.
3. Advanced tab, **Jumbo Packet**, set to **9014 Bytes**, OK.

The link drops for a few seconds while it applies. Set it back to Disabled to undo.
