#!/usr/bin/env python3
"""Narrate every story segment with edge-tts.

Writes audio/<id>.mp3 + audio/<id>.srt (real word timings) + audio/<id>.txt
(text fingerprint), measures durations, and emits build/segments.json.

Re-running only regenerates segments whose text changed, unless --force.
"""
import argparse
import hashlib
import subprocess
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import lib  # noqa: E402


def synth(bin_path, seg, voice, rate, volume, force):
    mp3 = lib.AUDIO / f"{seg['id']}.mp3"
    srt = lib.AUDIO / f"{seg['id']}.srt"
    txt = lib.AUDIO / f"{seg['id']}.txt"
    digest = hashlib.sha256(
        f"{voice}|{rate}|{volume}|{seg['text']}".encode()).hexdigest()[:16]
    if not force and mp3.exists() and txt.exists() and srt.exists():
        if txt.read_text().strip() == digest:
            return lib.ffprobe_duration(mp3), "cached"
    for attempt in range(1, 4):
        for p in (mp3, srt):
            p.unlink(missing_ok=True)
        try:
            subprocess.run([
                bin_path, f"--voice={voice}", f"--rate={rate}",
                f"--volume={volume}", f"--text={seg['text']}",
                f"--write-media={mp3}", f"--write-subtitles={srt}",
            ], capture_output=True, text=True, timeout=180, check=True)
        except Exception as e:
            msg = getattr(e, "stderr", "") or str(e)
            print(f"  ! {seg['id']} attempt {attempt} failed: {str(msg)[-160:]}",
                  file=sys.stderr, flush=True)
            time.sleep(2 * attempt)
            continue
        if mp3.exists() and srt.exists() and mp3.stat().st_size > 2000:
            txt.write_text(digest)
            return lib.ffprobe_duration(mp3), "new"
        print(f"  ! {seg['id']} attempt {attempt}: incomplete output", flush=True)
        time.sleep(2 * attempt)
    sys.exit(f"edge-tts failed for {seg['id']} after 3 attempts "
             "(check network access to speech.platform.bing.com)")


def main():
    ap = argparse.ArgumentParser()
    lib.project_arg(ap)
    ap.add_argument("--force", action="store_true", help="regenerate all audio")
    ap.add_argument("--only", nargs="*", default=None, help="segment ids")
    args = ap.parse_args()

    lib.init(args.project)
    lib.ensure_dirs()
    print(f"project: {lib.project_label()}")
    cfg = lib.load_config()
    story = lib.load_story()
    voice = story.get("voice", cfg["voice"])
    rate = story.get("rate", cfg["rate"])
    volume = story.get("volume", cfg["volume"])
    bin_path = lib.edge_tts_bin()

    segments, total = [], 0.0
    for seg in story["segments"]:
        if args.only and seg["id"] not in args.only:
            segments.append({**seg, "audio": None, "srt": None, "dur": None})
            continue
        dur, how = synth(bin_path, seg, voice, rate, volume, args.force)
        segments.append({
            "id": seg["id"], "text": seg["text"], "scene": seg.get("scene"),
            "audio": str(lib.AUDIO / f"{seg['id']}.mp3"),
            "srt": str(lib.AUDIO / f"{seg['id']}.srt"),
            "dur": dur,
        })
        total += dur + cfg["pad"]
        print(f"  {seg['id']:<16} {dur:6.2f}s  {how}", flush=True)

    # keep previous metadata for segments we skipped with --only
    old = {}
    if (lib.BUILD / "segments.json").exists():
        old = {s["id"]: s for s in lib.load_json(lib.BUILD / "segments.json")}
    for i, s in enumerate(segments):
        if s["dur"] is None:
            if s["id"] not in old:
                sys.exit(f"--only skipped {s['id']} but no previous audio exists; "
                         "run without --only first")
            segments[i] = old[s["id"]]

    lib.save_json(lib.BUILD / "segments.json", segments)
    total = sum(s["dur"] + cfg["pad"] for s in segments)
    print(f"narration: {len(segments)} segments, {total:.1f}s total "
          f"(voice {voice}, rate {rate})")


if __name__ == "__main__":
    main()
