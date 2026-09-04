"""الطلبُ والردّ كما تراهما طبقةُ التطبيق — بلا مقبسٍ ولا ترويسةٍ خام.

المعالِجُ يأخذ `Request` ويعيد `Response`. لا يعرف كيف تُكتب كعكةٌ ولا كيف
يُغلق اتصال؛ يقول «اضبط الجلسة بهذا الرمز» و«هذا ملفٌّ من هذا النوع»،
وطبقةُ HTTP هي التي تُنفّذ. وبهذا يُنادى كلُّ معالِجٍ في اختبارٍ بلا خادم.
"""
import sqlite3

class Response:
    """جسمٌ ورمزُ حالة، ومعهما نيّةٌ في الكعكة أو ملفٌّ يُقدَّم."""
    __slots__ = ("body", "code", "headers", "cookie", "file")

    def __init__(self, body=None, code=200, headers=(), cookie=None, file=None):
        self.body, self.code = body, code
        self.headers = list(headers)
        self.cookie = cookie          # None · ("set", token, ttl) · ("clear",)
        self.file = file              # None · (المسار، نوعُ المحتوى)

    @classmethod
    def json(cls, body, code=200, headers=()):
        return cls(body, code, headers)

    @classmethod
    def sends_file(cls, path, ctype):
        return cls(None, 200, file=(path, ctype))

class Request:
    """كلُّ ما يحتاجه معالِجٌ ليعمل — ولا شيءَ فوقه.

    `content` تُفتح عند أوّل طلبٍ لها وتُغلق مع الطلب: مساراتُ الحساب
    والمشاريع لا تلمس قاعدةَ المحتوى أصلًا، فلا يُفتح لها اتصال.
    """
    __slots__ = ("path", "method", "query", "body", "user", "subject", "c",
                 "root", "content_db", "params", "get_header", "client_ip",
                 "session_token", "_content")

    def __init__(self, *, path, method, query, body, c, root, content_db,
                 user=None, subject=None, get_header=None, client_ip="-",
                 session_token=None):
        self.path, self.method = path, method
        self.query, self.body = query, body
        self.c, self.root, self.content_db = c, root, content_db
        self.user, self.subject = user, subject
        self.get_header = get_header or (lambda name, default=None: default)
        self.client_ip, self.session_token = client_ip, session_token
        self.params = {}
        self._content = None

    @property
    def uid(self):
        return self.user["id"] if self.user else None

    @property
    def content(self):
        if self._content is None:
            self._content = sqlite3.connect(f"file:{self.content_db}?mode=ro", uri=True)
            self._content.row_factory = sqlite3.Row
        return self._content

    def close(self):
        if self._content is not None:
            self._content.close(); self._content = None
