"""إرسال البريد — بـSMTP إن ضُبط، وإلى ملفٍّ محليٍّ إن لم يُضبط.

لا يُدَّعى إرسالٌ لم يقع: إن لم يُضبط SMTP كُتبت الرسالة في `outbox/`
وأُعيدت `sent=False`، فيعرف الخادم أن الرسالة لم تُرسل فعلًا ويقول ذلك.

المتغيّرات: FALAH_SMTP_HOST · FALAH_SMTP_PORT · FALAH_SMTP_USER ·
FALAH_SMTP_PASS · FALAH_MAIL_FROM · FALAH_ORIGIN
"""
import os, smtplib, ssl, time
from email.message import EmailMessage

HERE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTBOX = os.path.join(HERE, "outbox")
HOST   = os.environ.get("FALAH_SMTP_HOST", "")
PORT   = int(os.environ.get("FALAH_SMTP_PORT", "587"))
USER   = os.environ.get("FALAH_SMTP_USER", "")
PASS   = os.environ.get("FALAH_SMTP_PASS", "")
SENDER = os.environ.get("FALAH_MAIL_FROM", "falah@localhost")
ORIGIN = os.environ.get("FALAH_ORIGIN", "").rstrip("/")

def configured():
    return bool(HOST and SENDER)

def send(to, subject, body):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = SENDER, to, subject
    m.set_content(body)
    if not configured():
        os.makedirs(OUTBOX, exist_ok=True)
        p = os.path.join(OUTBOX, f"{int(time.time())}-{abs(hash(to)) % 10**6}.eml")
        open(p, "w", encoding="utf-8").write(m.as_string())
        return {"sent": False, "reason": "SMTP غير مضبوط", "file": os.path.basename(p)}
    try:
        with smtplib.SMTP(HOST, PORT, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if USER: s.login(USER, PASS)
            s.send_message(m)
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "reason": type(e).__name__}

def link(path, token):
    base = ORIGIN or "http://localhost:8080"
    return f"{base}{path}?t={token}"

def reset_mail(to, token):
    return send(to, "استعادة كلمة المرور — فَلاح",
        "وصلنا طلبٌ لاستعادة كلمة مرور حسابك في فَلاح.\n\n"
        f"افتح هذا الرابط خلال ساعة:\n{link('/reset', token)}\n\n"
        "إن لم تطلب هذا فتجاهل الرسالة؛ لم يتغيّر شيءٌ في حسابك.")

def verify_mail(to, token):
    return send(to, "تأكيد البريد — فَلاح",
        "أهلًا بك في فَلاح.\n\n"
        f"أكّد بريدك بفتح هذا الرابط خلال يومين:\n{link('/verify', token)}\n\n"
        "التأكيد يتيح استعادة كلمة المرور إن نسيتها.")
