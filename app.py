"""Human detection and calibrated speed monitoring desktop application."""

from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk
import pygame
from ultralytics import YOLO

from speed_estimator import SpeedEstimator


TRACKED_CLASSES = {0}  # COCO: person


@dataclass
class FrameResult:
    frame: object
    speed_kph: float
    elapsed_seconds: float | None
    vehicles: int
    status: str = "Running"
    overspeed_ids: frozenset[int] = frozenset()
    direction: str | None = None


class VehicleMonitor:
    def __init__(self, root: tk.Tk, camera: int, model_name: str):
        self.root = root
        self.camera_index = camera
        self.model_name = model_name
        self.results: queue.Queue[FrameResult] = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.photo = None
        self.blink_on = False
        self.audio_file: Path | None = None
        self.active_overspeed_ids: set[int] = set()
        self.speed_display_until = 0.0
        self.displayed_speed = 0.0
        self.displayed_elapsed: float | None = None
        self.displayed_direction: str | None = None

        root.title("Human Speed Monitor")
        root.geometry("1100x720")
        root.minsize(820, 580)
        root.configure(bg="#111418")
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.speed_var = tk.StringVar(value="--.- km/h")
        self.time_var = tk.StringVar(value="Direction: -- | Time: --.-- s")
        self.count_var = tk.StringVar(value="0 people")
        self.status_var = tk.StringVar(value="Starting camera...")
        self.audio_var = tk.StringVar(value="No alert audio selected")
        self.distance_var = tk.DoubleVar(value=10.0)
        self.limit_var = tk.DoubleVar(value=10.0)
        self.line_a_var = tk.IntVar(value=35)
        self.line_b_var = tk.IntVar(value=65)
        self.settings = {"distance": 10.0, "limit": 10.0, "line_a": 35.0,
                         "line_b": 65.0}
        self.distance_var.trace_add("write", self._sync_settings)
        self.limit_var.trace_add("write", self._sync_settings)
        self.line_a_var.trace_add("write", self._sync_settings)
        self.line_b_var.trace_add("write", self._sync_settings)

        self._build_ui()
        self.start()
        self.root.after(30, self._poll_results)
        self.root.after(350, self._blink_alert)

    def _sync_settings(self, *_args: object) -> None:
        try:
            self.settings = {
                "distance": max(0.1, float(self.distance_var.get())),
                "limit": max(1.0, float(self.limit_var.get())),
                "line_a": min(85.0, max(5.0, float(self.line_a_var.get()))),
                "line_b": min(95.0, max(15.0, float(self.line_b_var.get()))),
            }
        except (tk.TclError, ValueError):
            # A Spinbox is temporarily empty while the user edits it.
            pass

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Panel.TFrame", background="#1b2026")
        style.configure("TLabel", background="#1b2026", foreground="#dce2e8")
        style.configure("TScale", background="#1b2026")

        main = ttk.Frame(self.root, style="Panel.TFrame")
        main.pack(fill="both", expand=True)
        self.video = tk.Label(main, bg="#050607", bd=0)
        self.video.pack(side="left", fill="both", expand=True)

        panel = ttk.Frame(main, width=270, padding=20, style="Panel.TFrame")
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)

        ttk.Label(panel, text="LIVE SPEED", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(panel, textvariable=self.speed_var, font=("TkDefaultFont", 27, "bold")).pack(anchor="w", pady=(4, 2))
        ttk.Label(panel, textvariable=self.time_var).pack(anchor="w", pady=(0, 2))
        ttk.Label(panel, textvariable=self.count_var).pack(anchor="w", pady=(0, 18))

        self.alert = tk.Label(
            panel,
            text="SPEED LIMIT",
            font=("TkDefaultFont", 15, "bold"),
            bg="#343a40",
            fg="white",
            height=3,
        )
        self.alert.pack(fill="x", pady=(0, 24))

        ttk.Label(panel, text="Speed limit (km/h)").pack(anchor="w")
        ttk.Spinbox(panel, from_=1, to=200, textvariable=self.limit_var, width=10).pack(anchor="w", pady=(4, 16))
        ttk.Label(panel, text="Real A-B distance (meters)").pack(anchor="w")
        ttk.Spinbox(
            panel, from_=0.1, to=1000.0, increment=0.5, textvariable=self.distance_var, width=10
        ).pack(anchor="w", pady=(4, 4))
        ttk.Label(panel, text="Enter the measured road distance between green lines A and B.", wraplength=225).pack(anchor="w", pady=(0, 18))

        ttk.Label(panel, text="Line A horizontal position").pack(anchor="w")
        ttk.Scale(panel, from_=5, to=85, variable=self.line_a_var, orient="horizontal").pack(fill="x", pady=(4, 10))
        ttk.Label(panel, text="Line B horizontal position").pack(anchor="w")
        ttk.Scale(panel, from_=15, to=95, variable=self.line_b_var, orient="horizontal").pack(fill="x", pady=(4, 14))

        ttk.Label(panel, text="Overspeed alert audio").pack(anchor="w")
        ttk.Label(panel, textvariable=self.audio_var, wraplength=225).pack(anchor="w", pady=(3, 5))
        audio_buttons = ttk.Frame(panel, style="Panel.TFrame")
        audio_buttons.pack(fill="x", pady=(0, 12))
        ttk.Button(audio_buttons, text="Choose audio...", command=self._choose_audio).pack(side="left")
        ttk.Button(audio_buttons, text="Test", command=self._play_audio).pack(side="left", padx=(7, 0))
        ttk.Label(panel, textvariable=self.status_var, wraplength=225).pack(side="bottom", anchor="w")

    def _choose_audio(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Choose overspeed alert audio",
            filetypes=(
                ("Audio files", "*.wav *.mp3 *.ogg"),
                ("WAV files", "*.wav"),
                ("MP3 files", "*.mp3"),
                ("OGG files", "*.ogg"),
                ("All files", "*.*"),
            ),
        )
        if filename:
            self.audio_file = Path(filename)
            self.audio_var.set(self.audio_file.name)

    def _play_audio(self) -> None:
        if self.audio_file is None:
            messagebox.showinfo("Alert Audio", "Choose an audio file first.", parent=self.root)
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            pygame.mixer.music.load(str(self.audio_file))
            pygame.mixer.music.play()
        except (OSError, pygame.error) as exc:
            messagebox.showerror(
                "Alert Audio", f"Could not play the selected audio file:\n{exc}", parent=self.root
            )

    def start(self) -> None:
        self.worker = threading.Thread(target=self._capture_loop, daemon=True)
        self.worker.start()

    def _capture_loop(self) -> None:
        capture = cv2.VideoCapture(self.camera_index)
        if not capture.isOpened():
            self._publish(FrameResult(None, 0.0, None, 0,
                                      f"Cannot open camera {self.camera_index}"))
            return
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        estimator = SpeedEstimator(self.settings["distance"])
        try:
            model = YOLO(self.model_name)
            while not self.stop_event.is_set():
                settings = self.settings
                ok, frame = capture.read()
                if not ok:
                    self._publish(FrameResult(None, 0.0, None, 0,
                                              "Camera frame unavailable"))
                    time.sleep(0.2)
                    continue

                frame = cv2.flip(frame, 1)

                now = time.monotonic()
                estimator.distance_meters = settings["distance"]
                tracked = model.track(
                    frame, persist=True, classes=list(TRACKED_CLASSES), verbose=False
                )[0]
                height, width = frame.shape[:2]
                line_a_x = int(width * settings["line_a"] / 100)
                line_b_x = int(width * settings["line_b"] / 100)
                cv2.line(frame, (line_a_x, 0), (line_a_x, height), (30, 210, 30), 3)
                cv2.line(frame, (line_b_x, 0), (line_b_x, height), (30, 210, 30), 3)
                cv2.putText(frame, "A", (line_a_x + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (30, 210, 30), 2)
                cv2.putText(frame, "B", (line_b_x + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (30, 210, 30), 2)

                completed_measurements: list[tuple[float, float, str | None]] = []
                overspeed_ids: set[int] = set()
                boxes = tracked.boxes
                if boxes is not None and boxes.id is not None:
                    ids = boxes.id.int().cpu().tolist()
                    coords = boxes.xyxy.cpu().tolist()
                    classes = boxes.cls.int().cpu().tolist()
                    for track_id, (x1, y1, x2, y2), class_id in zip(ids, coords, classes):
                        center = ((x1 + x2) / 2, (y1 + y2) / 2)
                        measurement = estimator.update(track_id, center[0], line_a_x, line_b_x, now)
                        speed = measurement.speed_kph
                        color = (40, 40, 235) if speed > settings["limit"] else (55, 205, 80)
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        cv2.circle(frame, (int(center[0]), int(center[1])), 7, (0, 140, 255), -1)
                        state = " timing" if measurement.timing else ""
                        direction = f" {measurement.direction}" if measurement.direction else ""
                        label = f"{model.names[class_id]} #{track_id}  {speed:.1f} km/h{direction}{state}"
                        cv2.putText(frame, label, (int(x1), max(22, int(y1) - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.56, color, 2)
                        if speed > 0.0:
                            if measurement.completed and measurement.elapsed_seconds is not None:
                                completed_measurements.append(
                                    (speed, measurement.elapsed_seconds, measurement.direction)
                                )
                            if speed > settings["limit"]:
                                overspeed_ids.add(track_id)
                estimator.prune(now)
                speed, elapsed, direction = max(
                    completed_measurements,
                    default=(0.0, None, None),
                    key=lambda item: item[0],
                )
                count = 0 if boxes is None else len(boxes)
                self._publish(FrameResult(frame, speed, elapsed, count,
                                          f"Running: camera {self.camera_index}",
                                          frozenset(overspeed_ids), direction))
        except Exception as exc:
            self._publish(FrameResult(None, 0.0, None, 0, f"Model error: {exc}"))
        finally:
            capture.release()

    def _publish(self, result: FrameResult) -> None:
        if self.results.full():
            try:
                self.results.get_nowait()
            except queue.Empty:
                pass
        self.results.put_nowait(result)

    def _poll_results(self) -> None:
        latest = None
        try:
            while True:
                latest = self.results.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            self.status_var.set(latest.status)
            person_label = "person" if latest.vehicles == 1 else "people"
            self.count_var.set(f"{latest.vehicles} {person_label}")
            if latest.elapsed_seconds is not None:
                self.displayed_speed = latest.speed_kph
                self.displayed_elapsed = latest.elapsed_seconds
                self.displayed_direction = latest.direction
                self.speed_display_until = time.monotonic() + 2.0
            new_overspeed_ids = latest.overspeed_ids - self.active_overspeed_ids
            self.active_overspeed_ids = set(latest.overspeed_ids)
            if new_overspeed_ids and self.audio_file is not None:
                self._play_audio()
            if latest.frame is not None:
                rgb = cv2.cvtColor(latest.frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb)
                max_w = max(320, self.video.winfo_width())
                max_h = max(240, self.video.winfo_height())
                image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                self.photo = ImageTk.PhotoImage(image)
                self.video.configure(image=self.photo)

        if time.monotonic() < self.speed_display_until:
            self.current_speed = self.displayed_speed
            self.speed_var.set(f"{self.displayed_speed:.1f} km/h")
            self.time_var.set(
                f"Direction: {self.displayed_direction or '--'} | "
                f"Time: {self.displayed_elapsed:.2f} s"
            )
        else:
            self.current_speed = 0.0
            self.speed_var.set("--.- km/h")
            self.time_var.set("Direction: -- | Time: --.-- s")
        if not self.stop_event.is_set():
            self.root.after(30, self._poll_results)

    def _blink_alert(self) -> None:
        overspeed = getattr(self, "current_speed", 0.0) > self.limit_var.get()
        self.blink_on = not self.blink_on if overspeed else False
        self.alert.configure(
            bg="#e31b23" if overspeed and self.blink_on else "#343a40",
            text="OVER SPEED" if overspeed else "SPEED LIMIT",
        )
        if not self.stop_event.is_set():
            self.root.after(350, self._blink_alert)

    def close(self) -> None:
        self.stop_event.set()
        if pygame.mixer.get_init() is not None:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Webcam human speed monitor")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--model", default="yolov8n.pt", help="Ultralytics model path/name")
    args = parser.parse_args()
    root = tk.Tk()
    try:
        VehicleMonitor(root, args.camera, args.model)
        root.mainloop()
    except tk.TclError as exc:
        messagebox.showerror("Human Speed Monitor", str(exc))


if __name__ == "__main__":
    main()
