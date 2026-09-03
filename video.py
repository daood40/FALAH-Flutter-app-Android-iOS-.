#!/usr/bin/env python3
"""محرّك الفيديو — بطاقةٌ مفحوصة + تلاوة قارئ ← مقطع جاهز للنشر.

    python3 video.py --surah 94 --ayah 5 --to 6 --reciter alafasy --ratio vertical

الصوت يُجلب من رابط القارئ المسجَّل في القاعدة، والصورة من محرّك التصيير
نفسه، فما يظهر في الفيديو هو نفس ما اجتاز الفحوص الخمسة والعشرين.
"""
import argparse, os, subprocess, sys, tempfile, urllib.request, sqlite3, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
from falah.audio import audio_url

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "falah.db")

def ffmpeg_bin():
    """يُفضَّل بناءٌ كامل: نسخة Playwright المختصرة تفتقر مرشّح concat."""
    import shutil
    for p in ("/usr/bin/ffmpeg", shutil.which("ffmpeg")):
        if p and os.path.exists(p): return p
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception: pass
    raise SystemExit("ffmpeg غير موجود — ثبّته: apt-get install ffmpeg")

def ffprobe_bin():
    import shutil
    return shutil.which("ffprobe") or "/usr/bin/ffprobe"

def ayah_audio(surah, ayah, reciter):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM reciters WHERE code=?", (reciter,)).fetchone()
    idx = c.execute("SELECT id FROM ayat WHERE surah=? AND ayah=?", (surah, ayah)).fetchone()
    c.close()
    if not r:   raise SystemExit("القارئ غير مسجَّل")
    if not idx: raise SystemExit("الآية غير موجودة")
    return r["name"], audio_url(r["scheme"], r["folder"], surah, ayah, idx["id"])

def fetch(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path

def build(surah, ayah, to, reciter, skin, ratio, wm, out, fade=0.6, tail=1.2):
    to = to or ayah
    card, rep = R.fetch_card("quran", surah=surah, ayah=ayah, to=to)
    html = R.build_html(card, "quran", skin, ratio, wm)
    tmp  = tempfile.mkdtemp()
    png  = R.render(html, os.path.join(tmp, "card.png"), ratio)

    # صوت كل آية في المدى، ثم تُدمج بالترتيب
    parts, names = [], []
    for a in range(ayah, to + 1):
        name, url = ayah_audio(surah, a, reciter)
        names.append(name)
        parts.append(fetch(url, os.path.join(tmp, f"{a}.mp3")))
    ff, probe = ffmpeg_bin(), ffprobe_bin()
    audio = os.path.join(tmp, "audio.m4a")
    if len(parts) == 1:
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", parts[0],
                        "-c:a", "aac", "-b:a", "192k", audio], check=True)
    else:
        ins = sum([["-i", p] for p in parts], [])
        chain = "".join(f"[{i}:a]" for i in range(len(parts)))
        subprocess.run([ff, "-y", "-loglevel", "error"] + ins +
                       ["-filter_complex", f"{chain}concat=n={len(parts)}:v=0:a=1[a]",
                        "-map", "[a]", "-c:a", "aac", "-b:a", "192k", audio], check=True)
    dur = float(subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nw=1:nk=1", audio],
                               capture_output=True, text=True).stdout.strip() or 0)
    total = dur + tail
    subprocess.run([ff, "-y", "-loglevel", "error",
        "-loop", "1", "-i", png, "-i", audio,
        "-filter_complex",
        f"[0:v]scale={R.SIZES[ratio][0]}:{R.SIZES[ratio][1]},"
        f"fade=t=in:st=0:d={fade},fade=t=out:st={max(total-fade,0):.2f}:d={fade},format=yuv420p[v];"
        f"[1:a]afade=t=out:st={max(dur-0.4,0):.2f}:d=0.4,apad=pad_dur={tail}[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)
    return out, names[0], dur, rep

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--surah", type=int, required=True); p.add_argument("--ayah", type=int, required=True)
    p.add_argument("--to", type=int); p.add_argument("--reciter", default="alafasy")
    p.add_argument("--skin", default="parch", choices=list(R.SKINS))
    p.add_argument("--ratio", default="vertical", choices=list(R.SIZES))
    p.add_argument("--wm", default="قناتك"); p.add_argument("--out", default="clip.mp4")
    n = p.parse_args()
    out, reciter, dur, rep = build(n.surah, n.ayah, n.to, n.reciter, n.skin, n.ratio, n.wm, n.out)
    w, h = R.SIZES[n.ratio]
    print(f"✓ {out}  {w}×{h}  · {dur:.1f}ث بصوت {reciter} · اجتاز {rep['passed']}/{rep['total']} فحصًا")
