"""يسحب أحاديث الموسوعة بشرحها وفوائدها وترجماتها."""
import json, urllib.request, concurrent.futures as cf, time, os
LANGS = ["ar", "en"]
req = lambda u: urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0 (FALAH content builder)"})
def get(u, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(req(u), timeout=30) as r: return json.load(r)
        except Exception: time.sleep(1.0*(i+1))
    return None
ids = json.load(open("raw/enc/ids.json"))
for lang in LANGS:
    out = f"raw/enc/{lang}.json"
    if os.path.exists(out) and os.path.getsize(out) > 50000: 
        print(f"{lang}: موجود"); continue
    t0 = time.time(); res = {}
    def one(i, lang=lang):        # يُربط الآن لا عند النداء
        d = get(f"https://hadeethenc.com/api/v1/hadeeths/one/?language={lang}&id={i}")
        return i, d
    with cf.ThreadPoolExecutor(16) as ex:
        for i, d in ex.map(one, ids):
            if d: res[i] = d
    json.dump(res, open(out,"w"), ensure_ascii=False)
    print(f"{lang}: {len(res)}/{len(ids)}  {os.path.getsize(out)//1024}KB  ({time.time()-t0:.0f}s)")
