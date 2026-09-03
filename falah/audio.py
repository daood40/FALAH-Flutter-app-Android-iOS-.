"""القرّاء والتلاوات — آيةً آية.

لا تُنزَّل ملفات الصوت (عشرات الجيجابايتات)، بل يُخزَّن القارئ وقالبُ
رابطه، ويُبنى الرابط عند الطلب. هكذا تبقى القاعدة صغيرة، ويظلّ لكل آية
تلاوةٌ من كل قارئ مسجَّل.
"""

# قالب الرابط: {s} رقم السورة بثلاث خانات · {a} رقم الآية بثلاث · {n} الرقم المتسلسل
EVERYAYAH = "https://everyayah.com/data/{folder}/{s:03d}{a:03d}.mp3"
CLOUD     = "https://cdn.islamic.network/quran/audio/{bitrate}/{edition}/{n}.mp3"

# قارئٌ واحدٌ في السطر: المعرّف · الاسم · الرواية · قالب الرابط ومعاملاته
RECITERS = [
    # ── حفص عن عاصم ──
    ("alafasy",      "مشاري راشد العفاسي",        "حفص عن عاصم", "everyayah", "Alafasy_128kbps"),
    ("husary",       "محمود خليل الحصري",          "حفص عن عاصم", "everyayah", "Husary_128kbps"),
    ("husary_muj",   "محمود خليل الحصري (مجوّد)",  "حفص عن عاصم", "everyayah", "Husary_Mujawwad_64kbps"),
    ("minshawi",     "محمد صديق المنشاوي",         "حفص عن عاصم", "everyayah", "Minshawy_Murattal_128kbps"),
    ("minshawi_muj", "محمد صديق المنشاوي (مجوّد)", "حفص عن عاصم", "everyayah", "Minshawy_Mujawwad_192kbps"),
    ("abdulbasit",   "عبد الباسط عبد الصمد",       "حفص عن عاصم", "everyayah", "Abdul_Basit_Murattal_192kbps"),
    ("abdulbasit_m", "عبد الباسط عبد الصمد (مجوّد)","حفص عن عاصم", "everyayah", "Abdul_Basit_Mujawwad_128kbps"),
    ("sudais",       "عبد الرحمن السديس",          "حفص عن عاصم", "everyayah", "Abdurrahmaan_As-Sudais_192kbps"),
    ("shuraim",      "سعود الشريم",                "حفص عن عاصم", "everyayah", "Saood_ash-Shuraym_128kbps"),
    ("maher",        "ماهر المعيقلي",              "حفص عن عاصم", "everyayah", "MaherAlMuaiqly128kbps"),
    ("shatri",       "أبو بكر الشاطري",            "حفص عن عاصم", "everyayah", "Abu_Bakr_Ash-Shaatree_128kbps"),
    ("ajamy",        "أحمد بن علي العجمي",         "حفص عن عاصم", "everyayah", "ahmed_ibn_ali_al_ajamy_128kbps"),
    ("hudhaify",     "علي الحذيفي",                "حفص عن عاصم", "everyayah", "Hudhaify_128kbps"),
    ("rifai",        "هاني الرفاعي",               "حفص عن عاصم", "everyayah", "Hani_Rifai_192kbps"),
    ("basfar",       "عبد الله بصفر",              "حفص عن عاصم", "everyayah", "Abdullah_Basfar_192kbps"),
    ("akhdar",       "إبراهيم الأخضر",             "حفص عن عاصم", "everyayah", "Ibrahim_Akhdar_32kbps"),
    ("alafasy_cloud","مشاري العفاسي (نسخة بديلة)", "حفص عن عاصم", "cloud",  "ar.alafasy"),
    # ── روايات أخرى ──
    ("warsh_dossary",  "أبو الحارث الدوسري",  "ورش عن نافع",   "everyayah", "warsh/warsh_Abdul_Basit_128kbps"),
    ("warsh_yassin",   "ياسين الجزائري",       "ورش عن نافع",   "everyayah", "warsh/warsh_yassin_al_jazaery_64kbps"),
]

def audio_url(scheme, folder, surah, ayah, ayah_index, bitrate=128):
    if scheme == "everyayah":
        return EVERYAYAH.format(folder=folder, s=surah, a=ayah)
    return CLOUD.format(bitrate=bitrate, edition=folder, n=ayah_index)

def riwayat():
    out = {}
    for r in RECITERS: out.setdefault(r[2], []).append(r[1])
    return out
