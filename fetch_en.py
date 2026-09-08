import json, urllib.request, concurrent.futures as cf, time, os
req = lambda u: urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0 (FALAH)"})
def get(u, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(req(u), timeout=20) as r: return json.load(r)
        except Exception: time.sleep(0.6*(i+1))
    return None
ids = json.load(open("raw/enc/ids.json"))
out = "raw/enc/en.json"
res = json.load(open(out)) if os.path.exists(out) else {}
todo = [i for i in ids if i not in res]
def one(i): return i, get(f"https://hadeethenc.com/api/v1/hadeeths/one/?language=en&id={i}")
with cf.ThreadPoolExecutor(20) as ex:
    for n,(i,d) in enumerate(ex.map(one, todo),1):
        if d: res[i]=d
        if n % 400 == 0:
            json.dump(res, open(out,"w"), ensure_ascii=False)
json.dump(res, open(out,"w"), ensure_ascii=False)
print("en:", len(res))
