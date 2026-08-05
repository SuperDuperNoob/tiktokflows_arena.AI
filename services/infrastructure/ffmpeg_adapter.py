"""FFmpeg adapter for video processing."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import subprocess
import random
import json

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
from config import get_config


class FFmpegAdapter:
    """Adapter for FFmpeg operations."""

    def __init__(self):
        self.config = get_config()

    def get_encoding_params(self) -> Dict[str, str]:
        """Get encoding parameters from config."""
        return {
            "crf": str(get_config().get("encoding", "crf", default=23)),
            "maxrate": str(get_config().get("encoding", "maxrate", default="5M")),
            "bufsize": str(get_config().get("encoding", "bufsize", default="8M")),
            "abr": str(get_config().get("encoding", "abr", default="128k")),
            "preset": str(get_config().get("encoding", "preset", default="veryfast")),
            "threads": str(get_config().get("encoding", "threads", default=1)),
        }

    def probe_resolution(self, video_path: Path) -> tuple[int, int]:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_streams", "-of", "json", str(video_path)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=15)
        if r.returncode != 0:
            raise ValueError(r.stderr)
        stream = json.loads(r.stdout)["streams"][0]
        w, h = int(stream.get("width", 0)), int(stream.get("height", 0))
        for sd in stream.get("side_data_list", []):
            if sd.get("side_data_type") == "Display Matrix" and \
                    abs(int(sd.get("rotation", 0))) in (90, 270):
                return h, w
        return w, h

    def probe_duration(self, path: Path) -> float:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0.0
        except Exception:
            return 0.0

    def probe_frame_count(self, path: Path) -> int:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-count_packets", "-show_entries", "stream=nb_read_packets",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
        except Exception:
            return 0

    def encode(self, input_video: Path, output_video: Path, tmp_png: Optional[Path],
               sound_file: Optional[Path], width: int, height: int,
               speed: float, brightness: float, contrast: float,
               trim_start: float, overlay_y: float) -> tuple[bool, Optional[str]]:
        """Run ffmpeg encoding."""
        e = self.get_encoding_params()
        overlay_y_expr = f"(H-h)*{overlay_y:.3f}"
        vf = (
            f"[0:v]trim=start={trim_start:.2f},setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.3f},eq=brightness={brightness:.3f}:"
            f"contrast={contrast:.3f},scale=trunc(iw/2)*2:trunc(ih/2)*2[base];"
            f"[base][2:v]overlay=0:{overlay_y_expr}:format=auto:"
            f"eof_action=repeat[outv]"
        )
        cmd = ["ffmpeg", "-y", "-threads", e["threads"],
               "-i", str(input_video),
               "-stream_loop", "-1", "-i", str(sound_file),
               "-i", str(tmp_png),
               "-filter_complex", vf,
               "-map", "[outv]",
               "-map", "1:a",
               "-c:v", "libx264", "-crf", e["crf"], "-preset", e["preset"],
               "-maxrate", e["maxrate"], "-bufsize", e["bufsize"],
               "-pix_fmt", "yuv420p",
               "-profile:v", "high", "-level", "4.0",
               "-c:a", "aac", "-b:a", e["abr"], "-ar", "44100",
               "-shortest",
               "-movflags", "+faststart",
               str(output_video)]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, timeout=600)
            if res.returncode != 0:
                return False, res.stderr[-2000:]
            return True, None
        except subprocess.TimeoutExpired:
            return False, "ffmpeg timed out (>600s)"