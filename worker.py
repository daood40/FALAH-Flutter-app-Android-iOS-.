#!/usr/bin/env python3
"""عامل فلاح — يسحب مهامّ التصيير من الطابور وينفّذها خارج دورة الطلب.

    python3 worker.py                # عاملٌ واحد، يعمل حتى يُوقَف
    python3 worker.py --once         # مهمّةٌ واحدة ثم يخرج (للاختبار)
    python3 worker.py --drain        # يُفرغ الطابور ثم يخرج
    python3 worker.py --workers 2    # خيطان في العملية نفسها
    python3 worker.py --status       # حالة الطابور بلا تنفيذ

لا يُشارك الخادمَ ذاكرتَه ولا خيوطه — يمكن تشغيله على جهازٍ آخر ما دامت
`app.db` مشتركة. وإن مات في منتصف مهمّة عادت المهمّة إلى الطابور بعد
انقطاع نبضها (`jobs.reap`)، فلا يضيع عملٌ ولا يعلق «يجري» إلى الأبد.
"""
import argparse, json, os, signal, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from falah import store, jobs as J

DB   = os.environ.get("FALAH_DB", os.path.join(HERE, "falah.db"))
IDLE = float(os.environ.get("FALAH_WORKER_IDLE", 1.0))   # فترة النوم حين يخلو الطابور

_stop = threading.Event()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def loop(name, once=False, drain=False):
    """حلقة عاملٍ واحد. تنام حين يخلو الطابور فلا تُشغل المعالج بلا عمل."""
    last_reap = 0.0
    while not _stop.is_set():
        if time.time() - last_reap > 60:
            c = store.connect()
            try:
                n = J.reap(c)
                if n: log(f"أُعيدت {n} مهمّةً تركها عاملٌ منقطع")
            finally:
                c.close()
            last_reap = time.time()
        try:
            done = J.run_once(DB, HERE, worker=name)
        except Exception as e:                      # لا يسقط العامل بخطأ مهمّة
            log(f"خطأ في العامل: {type(e).__name__}: {e}")
            _stop.wait(IDLE); continue
        if done is None:
            if drain or once: return
            _stop.wait(IDLE); continue
        tag = "تمّ" if done.get("ok") else ("سيُعاد" if done.get("requeued") else "فشل")
        log(f"#{done['id']} {done['kind']} → {tag}"
            + (f" — {done.get('error')}" if not done.get("ok") else ""))
        if once: return

def status():
    c = store.connect()
    try:
        lines = [json.dumps(J.stats(c), ensure_ascii=False, indent=2)]
        for r in c.execute("""SELECT id,kind,state,progress,step,attempts,error
                              FROM jobs ORDER BY created_at DESC LIMIT 10"""):
            lines.append(f"  #{r['id']:<5} {r['kind']:<7} {r['state']:<9} "
                         f"{r['progress']:>3}%  {r['step'] or ''}  {r['error'] or ''}")
        try:    print("\n".join(lines))
        except BrokenPipeError: pass      # `| head` يغلق الأنبوب — ليس خطأً
    finally:
        c.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once",    action="store_true")
    ap.add_argument("--drain",   action="store_true")
    ap.add_argument("--status",  action="store_true")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("FALAH_WORKERS", 1)))
    a = ap.parse_args()

    store.init()
    if a.status: return status()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: (_stop.set(), log("يُنهي بعد المهمّة الجارية")))

    n = max(1, a.workers)
    log(f"عامل فلاح — {n} خيط · قاعدة {os.path.basename(store.APP_DB)}")
    if n == 1:
        loop(J.me(), a.once, a.drain)
    else:
        ts = [threading.Thread(target=loop, args=(f"{J.me()}#{i}", a.once, a.drain),
                               daemon=True) for i in range(n)]
        for t in ts: t.start()
        for t in ts: t.join()
    log("انتهى")

if __name__ == "__main__":
    main()
