#!/usr/bin/env python3
"""Validate the built video and produce visual QA artifacts.

Writes qa/contact_sheet.jpg, qa/frames/<id>.jpg, qa/report.txt and prints a
summary. Warnings are advisory; --strict turns them into a non-zero exit so
an agent can gate on them.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def extract_frames(video, segments, cfg):
    qa = lib.QA
    (qa / "frames").mkdir(parents=True, exist_ok=True)
    dur = lib.ffprobe_duration(video)
    step = max(1.0, dur / 16)
    lib.run(["ffmpeg", "-y", "-v", "error", "-i", video,
             "-vf", f"fps=1/{step:.3f},scale=480:-2,tile=4x4:padding=5:margin=5",
             "-frames:v", "1", "-q:v", "3", qa / "contact_sheet.jpg"])
    offset = 0.0
    for seg in segments:
        total = round(seg["dur"] + cfg["pad"], 2)
        t = offset + max(0.8, total * 0.5)
        lib.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
                 "-frames:v", "1", "-q:v", "3", qa / "frames" / f"{seg['id']}.jpg"])
        offset += total


def scan_stderr(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       cwd=str(lib.ROOT))
    return r.stderr


def main():
    ap = argparse.ArgumentParser()
    lib.project_arg(ap)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    lib.init(args.project)
    print(f"project: {lib.project_label()}")
    cfg = lib.load_config()
    video = lib.ROOT / cfg["output"]
    if not video.exists():
        sys.exit(f"missing {video} - run scripts/build.py first")

    warn, report = [], []
    p = lib.ffprobe_json(video)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    dur = float(p["format"]["duration"])
    size = int(p["format"].get("size", 0)) / 1e6
    if not v:
        warn.append("no video stream")
    if not a:
        warn.append("no audio stream")
    report.append(f"file       {video.relative_to(lib.ROOT)}")
    report.append(f"duration   {dur:.2f}s")
    if v:
        report.append(f"video      {v['width']}x{v['height']} "
                      f"{v['r_frame_rate']} {v.get('codec_name')}")
    if a:
        report.append(f"audio      {a.get('codec_name')} "
                      f"{a.get('sample_rate')}Hz")
    report.append(f"size       {size:.1f} MB")

    segments = lib.load_json(lib.BUILD / "segments.json")
    for seg in segments:
        clip = lib.CLIPS / f"{seg['id']}.webm"
        if not clip.exists():
            warn.append(f"{seg['id']}: clip missing")
            continue
        side = lib.CLIPS / f"{seg['id']}.json"
        trim = lib.load_json(side)["trim"] if side.exists() else cfg["trim"]
        need = trim + seg["dur"] + 1.0
        have = lib.ffprobe_duration(clip)
        if have + 0.05 < need:
            warn.append(f"{seg['id']}: clip {have:.1f}s < needed {need:.1f}s "
                        "(scene may end early)")

    stderr = scan_stderr(["ffmpeg", "-i", video, "-vf",
                          "blackdetect=d=0.6:pic_th=0.98:pix_th=0.02",
                          "-an", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", stderr)
    for s, e in blacks:
        warn.append(f"black gap {float(s):.1f}-{float(e):.1f}s")

    stderr = scan_stderr(["ffmpeg", "-i", video, "-af", "volumedetect",
                          "-vn", "-f", "null", "-"])
    stats = dict(re.findall(r"(\w+_volume):\s*(-?[\d.]+) dB", stderr))
    if stats:
        report.append(f"loudness   mean {stats.get('mean_volume')} dB  "
                      f"max {stats.get('max_volume')} dB")
        if stats.get("mean_volume") and float(stats["mean_volume"]) < -30:
            warn.append("audio is very quiet (mean < -30 dB)")
        if stats.get("max_volume") and float(stats["max_volume"]) >= -0.1:
            warn.append("audio may clip (max ~0 dB)")

    extract_frames(video, segments, cfg)
    report.append(f"contact    qa/contact_sheet.jpg  (16 frames)")
    report.append(f"frames     qa/frames/*.jpg  ({len(segments)} segments)")
    if warn:
        report.append("")
        report += [f"WARN  {w}" for w in warn]
    else:
        report.append("")
        report.append("PASS  no issues")
    (lib.QA / "report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    if warn and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
