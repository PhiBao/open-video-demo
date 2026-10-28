#!/usr/bin/env python3
"""Assemble the final video with ffmpeg.

clips/*.webm + audio/*.mp3 + build/segments.json
  -> per-segment trim + freeze-pad to narration length + mux audio
  -> concat -> burned subtitles + loudness normalization
  -> <output> (config/video.json) and a sidecar .srt
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def fallback_cues(text, dur):
    """Split narration across the segment when edge-tts wrote no SRT."""
    parts = [p for p in text.replace("!", ".").replace("?", ".").split(".") if p.strip()]
    total_chars = sum(len(p) for p in parts) or 1
    cues, t = [], 0.0
    for p in parts:
        span = dur * len(p) / total_chars
        cues.append((t, t + span, p.strip() + "."))
        t += span
    return cues


def segment_total(seg, cfg):
    """On-screen length of a segment.

    Normally the narration length plus a small pad. A scene whose own beats
    (clicks, waits for a slow app) outlast its narration is extended instead of
    truncated - the recorder writes the real action time next to the clip.
    """
    total = round(seg["dur"] + cfg["pad"], 2)
    side_file = lib.CLIPS / f"{seg['id']}.json"
    side = lib.load_json(side_file) if side_file.exists() else {}
    if side.get("action_time") is not None:
        # action_time is measured from the start of the clip; the build cuts
        # `trim` off the front, so compare what is left on screen.
        content = float(side["action_time"]) - float(side.get("trim", cfg["trim"]))
        total = round(max(total, content + 0.4), 2)
    return total


def segment_part(seg, cfg, work=None):
    work = work or lib.WORK
    sid = seg["id"]
    clip = lib.CLIPS / f"{sid}.webm"
    if not clip.exists():
        sys.exit(f"missing clip {clip} - run scripts/record.py first")
    side = lib.load_json(lib.CLIPS / f"{sid}.json") if (lib.CLIPS / f"{sid}.json").exists() else {}
    trim = float(side.get("trim", cfg["trim"]))
    total = segment_total(seg, cfg)
    w, h, fps = cfg["width"], cfg["height"], cfg["fps"]
    vf = (
        f"fps={fps},"
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"tpad=stop_mode=clone:stop_duration=10,format=yuv420p"
    )
    silent = work / f"{sid}_v.mp4"
    lib.run(["ffmpeg", "-y", "-v", "error", "-i", clip, "-ss", f"{trim:.2f}",
             "-vf", vf, "-t", f"{total:.2f}", "-an",
             "-c:v", "libx264", "-preset", cfg["preset"], "-crf", cfg["crf"],
             silent])
    out = work / f"{sid}.mp4"
    lib.run(["ffmpeg", "-y", "-v", "error", "-i", silent, "-i", seg["audio"],
             "-filter_complex", "[1:a]apad[a]", "-map", "0:v", "-map", "[a]",
             "-t", f"{total:.2f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             out])
    return out, total


def build_subtitles(segments, cfg):
    cues, offset = [], 0.0
    for seg in segments:
        total = segment_total(seg, cfg)
        srt_path = Path(seg.get("srt") or "")
        seg_cues = lib.parse_srt(srt_path) if srt_path.exists() else []
        if not seg_cues:
            seg_cues = fallback_cues(seg["text"], seg["dur"])
        for a, b, text in seg_cues:
            if not text:
                continue
            cues.append((offset + max(0.0, a), offset + min(seg["dur"] + 0.2, b), text))
        offset += total
    n = lib.write_srt(cues, lib.BUILD / "subs.srt")
    return n, offset


def concat(parts, out):
    listfile = lib.WORK / "concat.txt"
    listfile.write_text("".join(f"file '{p}'\n" for p in parts))
    lib.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", listfile, "-c", "copy", out])
    return out


def main():
    ap = argparse.ArgumentParser()
    lib.project_arg(ap)
    args = ap.parse_args()
    lib.init(args.project)
    lib.ensure_dirs()
    print(f"project: {lib.project_label()}")
    cfg = lib.load_config()
    segments = lib.load_segments()
    out_path = lib.ROOT / cfg["output"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    parts = []
    for seg in segments:
        part, total = segment_part(seg, cfg)
        parts.append(part)
        print(f"  {seg['id']:<16} {total:6.2f}s", flush=True)

    joined = concat(parts, lib.WORK / "joined.mp4")
    n, total = build_subtitles(segments, cfg)
    print(f"subtitles: {n} cues over {total:.1f}s")

    (lib.OUT / f"{cfg['name']}.srt").write_text((lib.BUILD / "subs.srt").read_text())

    burn = bool(cfg["burn_subtitles"])
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", joined]
    if burn:
        style = cfg["subtitle_style"].replace("'", "")
        cmd += ["-vf", f"subtitles=build/subs.srt:force_style='{style}'"]
    if cfg.get("loudness"):
        cmd += ["-af", f"loudnorm={cfg['loudness']}"]
    cmd += ["-c:v", "libx264" if burn else "copy"]
    if burn:
        cmd += ["-preset", cfg["preset"], "-crf", cfg["crf"], "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", str(out_path.relative_to(lib.ROOT))]
    lib.run(cmd)

    p = lib.ffprobe_json(out_path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    size = int(p["format"].get("size", 0)) / 1e6
    print(f"final: {out_path}  {float(p['format']['duration']):.1f}s  "
          f"{v['width']}x{v['height']} @ {v['r_frame_rate']}  "
          f"{'aac' if a else 'NO AUDIO'}  {size:.1f} MB")
    if burn:
        print("subs:  burned in (out/%s.srt also written)" % cfg["name"])


if __name__ == "__main__":
    main()
