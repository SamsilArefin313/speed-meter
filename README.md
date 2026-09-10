# Human Speed Monitor

A desktop webcam application that detects and tracks people only, draws two
vertical timing lines, measures their speed, and flashes a red alert when the
selected speed limit is exceeded.

## Setup

Python 3.10 or newer is recommended. On Linux, Tkinter may need to be installed
from the OS package manager (`python3-tk`).

For an IDE, open `run.py` and use its normal **Run** command. The launcher creates
a local `.venv`, installs the required packages on the first run, and starts the
application. Later runs reuse that environment.

Use **Choose audio...** in the control panel to select a WAV, MP3, or OGG alert.
The **Test** button previews it. Each tracked person plays the alert once when
their measured speed exceeds the configured limit.

Command-line options can be added to the IDE run configuration, for example
`--camera 1` or `--model /path/to/model.pt`.

To set up and run the application manually instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The app uses the default laptop camera (`camera 0`). On its first run,
Ultralytics downloads the small `yolov8n.pt` model. A different camera can be
selected with `python app.py --camera 1`.

## Calibration

Measure the real road distance represented between vertical lines A and B and
enter it in **Real A-B distance (meters)**. The orange center point starts the
timer when it crosses the first green line and stops it when it crosses the
other. Both left-to-right and right-to-left travel are supported. Speed is
calculated as `distance / elapsed time * 3.6`, and the completed direction is
shown as **A -> B** or **B -> A**. Each completed speed result remains on screen
for two seconds.

Keep the camera fixed and place both lines on the same ground plane. Camera
perspective and movement direction can otherwise make the measurement inaccurate.
