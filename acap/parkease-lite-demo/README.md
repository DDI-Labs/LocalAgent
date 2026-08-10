# ParkEase LITE — demo ACAP

A **UI-only demo** of the ParkEase LITE camera app, for showing customers what
the on-camera experience looks like. It installs on an Axis camera and appears
in the Apps list as "ParkEase LITE", serving the settings page mockup
(commissioning ticks, test buttons, simulated event feed) from the camera
itself.

**It has no real functionality.** The daemon is a sleep loop; the page is
static HTML with simulated data. It does not talk to Vaxtor, the A9210, or
ParkEase Cloud. The page itself carries no demo labelling — it is styled as
the finished product for presentation purposes, so be clear with the audience
that it is a preview. A "Lock & hide" button collapses the configuration
column (persisted in the browser via localStorage); "Show configuration"
brings it back.

## Build

Requires Docker. From this directory:

```sh
./build.sh              # armv7hf (default)
./build.sh aarch64      # for ARTPEC-8/9 cameras
```

The installable package lands in `out/ParkEase_LITE_0_1_0_<arch>.eap`.

## Install on the demo camera

1. Check the camera's architecture matches the build (`armv7hf` for ARTPEC-6/7
   era cameras such as the P1465-LE; `aarch64` for ARTPEC-8 and later).
2. Allow unsigned apps:
   - AXIS OS 11.x — Apps page → toggle **Allow unsigned apps**.
   - AXIS OS 12.x — enable developer mode / unsigned apps under
     **System → Maintenance** first.
3. Apps → **Add app** → upload the `.eap` → start it.
4. Open the app from the Apps list — the demo page is served at
   `http://<camera-ip>/local/parkease_lite/index.html`.

## Demo fallback

If installation fights you on the day, `html/index.html` is fully
self-contained — open it in any browser and present that instead; it is
pixel-identical to what the camera serves.
