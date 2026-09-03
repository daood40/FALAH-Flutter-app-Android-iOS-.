"""مشاريع المستخدم — وقفل المصدر ممتدًّا إليها.

المشروع لا يخزّن نصًّا: يخزّن *موضع* النصّ في قاعدة المحتوى وبصمته يوم
أُضيف. فإن صُحِّح المصدر لاحقًا — أو تغيّر حرفٌ في نسخةٍ جديدة من القاعدة —
انكسرت البصمة، فيُعلَم المستخدم أن نصّه انحرف عمّا اعتمده، ويُمنع التصدير
حتى يراجع الفرق بعينه. هذا امتدادٌ طبيعيّ لقاعدة التطبيق: لا شيء يُنشر
دون أن يُعرف من أين جاء وهل تغيّر.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from . import store
from . import verify as V
from .text import fingerprint

MAX_PROJECTS = 200
MAX_ITEMS    = 40

class ProjectError(Exception):
    """خطأ معروض للمستخدم."""

# ــــــــــــــــــــ جلب البطاقة من قاعدة المحتوى ــــــــــــــــــــ

def card_for(content, kind, ref):
    """يبني البطاقة ويفحصها. يعيد (البطاقة، التقرير) أو (None، None)."""
    import api
    if kind == "quran":
        it, ctx = api.quran_card(content, int(ref["surah"]), int(ref["ayah"]),
                                 int(ref["to"]) if ref.get("to") else None, True, True)
    elif kind == "enc":
        it, ctx = api.enc_card(content, int(ref["id"]))
    elif kind == "hadith":
        it, ctx = api.hadith_card(content, ref["book"], int(ref["no"]))
    else:
        raise ProjectError("نوع غير معروف")
    if not it: return None, None
    return it, V.run(it, ctx)

def ref_key(kind, ref):
    if kind == "quran": return f"quran:{ref['surah']}:{ref['ayah']}:{ref.get('to') or ''}"
    if kind == "enc":   return f"enc:{ref['id']}"
    return f"hadith:{ref['book']}:{ref['no']}"

# ــــــــــــــــــــ المشاريع ــــــــــــــــــــ

def create(c, user_id, title, kind="series", skin="night", ratio="square", watermark=None):
    title = (title or "").strip()[:120] or "مشروع بلا عنوان"
    n = c.execute("SELECT COUNT(*) n FROM projects WHERE user_id=? AND archived=0",
                  (user_id,)).fetchone()["n"]
    if n >= MAX_PROJECTS: raise ProjectError("بلغتَ حدّ المشاريع المفتوحة")
    t = store.now()
    cur = c.execute("""INSERT INTO projects(user_id,title,kind,skin,ratio,watermark,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (user_id, title, kind, skin, ratio, watermark, t, t))
    store.log(c, user_id, "project_created", title)
    c.commit()
    return cur.lastrowid

def owned(c, user_id, pid):
    r = c.execute("SELECT * FROM projects WHERE id=? AND user_id=?", (pid, user_id)).fetchone()
    if not r: raise ProjectError("المشروع غير موجود")
    return r

def listing(c, user_id, archived=0):
    out = []
    for r in c.execute("""SELECT p.*, (SELECT COUNT(*) FROM project_items i WHERE i.project_id=p.id) n
                          FROM projects p WHERE p.user_id=? AND p.archived=?
                          ORDER BY p.updated_at DESC""", (user_id, archived)):
        d = dict(r); d["items"] = d.pop("n"); out.append(d)
    return out

def update(c, user_id, pid, **kw):
    owned(c, user_id, pid)
    cols = [k for k in ("title", "kind", "skin", "ratio", "watermark", "note", "archived")
            if kw.get(k) is not None]
    if not cols: return
    sets = ", ".join(f"{k}=?" for k in cols) + ", updated_at=?"
    c.execute(f"UPDATE projects SET {sets} WHERE id=? AND user_id=?",
              [kw[k] for k in cols] + [store.now(), pid, user_id])
    c.commit()

def delete(c, user_id, pid):
    owned(c, user_id, pid)
    c.execute("DELETE FROM projects WHERE id=? AND user_id=?", (pid, user_id))
    store.log(c, user_id, "project_deleted", str(pid))
    c.commit()

# ــــــــــــــــــــ العناصر ــــــــــــــــــــ

def add_item(c, content, user_id, pid, kind, ref):
    """لا يُضاف إلى المشروع إلا ما اجتاز الفحوص كاملةً — الحجب عند الباب."""
    owned(c, user_id, pid)
    n = c.execute("SELECT COUNT(*) n FROM project_items WHERE project_id=?", (pid,)).fetchone()["n"]
    if n >= MAX_ITEMS: raise ProjectError("بلغتَ حدّ عناصر المشروع")
    card, rep = card_for(content, kind, ref)
    if not card: raise ProjectError("النصّ غير موجود في قاعدة المحتوى")
    if not rep["ok"]:
        raise ProjectError("محجوب — لم يجتز الفحص: " + "، ".join(rep["failed"]))
    key = ref_key(kind, ref)
    dup = c.execute("SELECT id FROM project_items WHERE project_id=? AND ref=?",
                    (pid, json.dumps(ref, ensure_ascii=False, sort_keys=True))).fetchone()
    if dup: raise ProjectError("هذا النصّ مضافٌ في المشروع")
    pos = (c.execute("SELECT COALESCE(MAX(pos),0) m FROM project_items WHERE project_id=?",
                     (pid,)).fetchone()["m"]) + 1
    cur = c.execute("""INSERT INTO project_items(project_id,pos,kind,ref,fp,checks,added_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (pid, pos, kind, json.dumps(ref, ensure_ascii=False, sort_keys=True),
                     fingerprint(card["text"]), f"{rep['passed']}/{rep['total']}", store.now()))
    c.execute("UPDATE projects SET updated_at=? WHERE id=?", (store.now(), pid))
    store.log(c, user_id, "item_added", key)
    c.commit()
    return cur.lastrowid

def remove_item(c, user_id, pid, item_id):
    owned(c, user_id, pid)
    c.execute("DELETE FROM project_items WHERE id=? AND project_id=?", (item_id, pid))
    c.execute("UPDATE projects SET updated_at=? WHERE id=?", (store.now(), pid))
    c.commit()

def reorder(c, user_id, pid, item_ids):
    owned(c, user_id, pid)
    have = {r["id"] for r in c.execute("SELECT id FROM project_items WHERE project_id=?", (pid,))}
    if set(item_ids) != have: raise ProjectError("قائمة الترتيب لا تطابق عناصر المشروع")
    for i, iid in enumerate(item_ids, start=1):
        c.execute("UPDATE project_items SET pos=? WHERE id=? AND project_id=?", (i, iid, pid))
    c.execute("UPDATE projects SET updated_at=? WHERE id=?", (store.now(), pid))
    c.commit()

# ــــــــــــــــــــ الفتح ومراجعة الانحراف ــــــــــــــــــــ

def open_project(c, content, user_id, pid):
    """يفتح المشروع ويعيد فحص كل عنصر الآن — لا يُوثَق بفحص الأمس وحده."""
    p = owned(c, user_id, pid)
    items, drift, blocked = [], [], []
    for r in c.execute("SELECT * FROM project_items WHERE project_id=? ORDER BY pos", (pid,)):
        ref = json.loads(r["ref"])
        card, rep = card_for(content, r["kind"], ref)
        d = {"id": r["id"], "pos": r["pos"], "kind": r["kind"], "ref": ref,
             "checks_then": r["checks"], "added_at": r["added_at"]}
        if not card:
            d["state"] = "missing"; d["why"] = "النصّ لم يعد في قاعدة المحتوى"
            blocked.append(d["id"])
        else:
            now_fp = fingerprint(card["text"])
            d["checks_now"] = f"{rep['passed']}/{rep['total']}"
            if now_fp != r["fp"]:
                d["state"] = "drift"
                d["why"]   = "تغيّر نصّ المصدر عمّا اعتمدتَه — راجع الفرق قبل النشر"
                d["fp_then"], d["fp_now"] = r["fp"], now_fp
                drift.append(d["id"]); blocked.append(d["id"])
            elif not rep["ok"]:
                d["state"] = "blocked"; d["why"] = "، ".join(rep["failed"])
                blocked.append(d["id"])
            else:
                d["state"] = "ok"
            d["card"] = card
        items.append(d)
    return {"project": dict(p), "items": items, "drift": drift, "blocked": blocked,
            "exportable": not blocked and bool(items)}

def accept_drift(c, content, user_id, pid, item_id):
    """موافقةٌ صريحة على النصّ الجديد — تُجدَّد البصمة ولا تُطمس القصّة."""
    owned(c, user_id, pid)
    r = c.execute("SELECT * FROM project_items WHERE id=? AND project_id=?",
                  (item_id, pid)).fetchone()
    if not r: raise ProjectError("العنصر غير موجود")
    card, rep = card_for(content, r["kind"], json.loads(r["ref"]))
    if not card or not rep["ok"]:
        raise ProjectError("النصّ الجديد نفسه لا يجتاز الفحص — لا يُعتمد")
    c.execute("UPDATE project_items SET fp=?, checks=?, added_at=? WHERE id=?",
              (fingerprint(card["text"]), f"{rep['passed']}/{rep['total']}", store.now(), item_id))
    store.log(c, user_id, "drift_accepted", f"{pid}:{item_id}:{r['fp']}→{fingerprint(card['text'])}")
    c.commit()

def record_export(c, user_id, pid, fmt, path, ratio=None, skin=None, checks=None):
    c.execute("""INSERT INTO exports(project_id,user_id,fmt,path,ratio,skin,checks,created_at)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (pid, user_id, fmt, path, ratio, skin, checks, store.now()))
    store.log(c, user_id, "export", f"{fmt}:{path}")
    c.commit()
