import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// ══════════════════ مفتاحُ التوقيع ══════════════════
//
// مفتاحُ الرفع يحكم كلَّ تحديثٍ لاحقٍ للتطبيق: من ملكه نشر باسمنا، ومن أضاعه
// لم يعد يستطيع تحديثَ تطبيقه في المتجر أبدًا. فلا يدخل المستودعَ ولا أيَّ
// محادثة، وإنما يُقرأ من `android/key.properties` (يمنعه `.gitignore`).
//
// ── تاريخُ هذا الملفّ، لأنّ فيه درسًا ──
//
// (١) كان أوّلًا: `signingConfig = debug` مع `// TODO`. فكان
//     `flutter build appbundle --release` **ينجح** ويُخرج حزمةً تبدو جاهزةً
//     للمتجر وهي موقَّعةٌ بمفتاحِ تصحيحٍ يملكه كلُّ من ثبَّت Android Studio.
//     عيبٌ لا يظهر إلا عند الرفع.
//
// (٢) ثم صار: توقيعٌ حقيقيٌّ إن وُجد المفتاح، وإلّا مفتاحُ تصحيحٍ مع لاحقة
//     `-debugsigned`. وهذا أصدقُ من الأوّل، **ولا يكفي**: ما زال ممكنًا أن
//     يُنتَج ملفٌّ اسمُه `app-release.aab` وهو موقَّعٌ بمفتاح تصحيح. والوسمُ
//     يُقرأ لمن نظر، ومن لم ينظر رفعه.
//
// (٣) وهذا هو القائم: **يستحيل إنتاجُ نسخةِ إنتاجٍ موقَّعةٍ بمفتاح تصحيح.**
//     المنافذُ ثلاثةٌ لا رابعَ لها:
//
//       المنفذ                          │ التوقيع        │ المعرِّف
//       ────────────────────────────────┼────────────────┼──────────────────────
//       production + مفتاحٌ موجود        │ مفتاحُ الرفع    │ com.falah.app
//       production + لا مفتاح            │ **يفشل البناء** │ —
//       staging (للتجربة)               │ مفتاحُ التصحيح  │ com.falah.app.staging
//
//     ففشلُ البناء صريحٌ برسالةٍ تقول ما ينقص وأين يُقرأ عنه، لا حزمةٌ صامتةٌ
//     يرفضها المتجرُ بعد شهر. ومنفذُ التجربة **معرِّفُه مختلف**، فلا يمكن أن
//     يُرفع مكانَ الإنتاج ولو أراد رافعُه: Play يعرف المعرِّفَ ولا يقبل غيره.
//
// راجع: docs/RELEASE_SIGNING.md

val keystoreProperties = Properties()
val keystoreFile = rootProject.file("key.properties")
val hasUploadKey = keystoreFile.exists()
if (hasUploadKey) {
    keystoreFile.inputStream().use { keystoreProperties.load(it) }
    // مفتاحٌ ناقصُ الحقول أسوأُ من غائب: يفشل في منتصف التوقيع برسالةٍ غامضة
    val missing = listOf("storePassword", "keyPassword", "keyAlias", "storeFile")
        .filter { keystoreProperties[it].toString().isBlank() }
    if (missing.isNotEmpty()) {
        throw GradleException(
            "\n✗ android/key.properties ناقصٌ: ${missing.joinToString("، ")}\n" +
            "  راجع docs/RELEASE_SIGNING.md\n"
        )
    }
    val ks = rootProject.file(keystoreProperties["storeFile"] as String)
    if (!ks.exists()) {
        throw GradleException(
            "\n✗ ملفُّ المخزن غير موجود: ${ks.absolutePath}\n" +
            "  `storeFile` في key.properties يشير إلى ملفٍّ لا وجودَ له.\n"
        )
    }
}

android {
    namespace = "com.falah.falah_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // معرّفٌ لا يتغيّر بعد أوّل رفعٍ للمتجر — يُثبَّت الآن
        applicationId = "com.falah.app"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        // لا يُنشَأ الإعدادُ إلا إن وُجد المفتاحُ فعلًا. وإعدادٌ يشير إلى ملفٍّ
        // غائبٍ يفشل متأخّرًا برسالةٍ غامضة، والغموضُ عدوُّ من يبني وحدَه.
        if (hasUploadKey) {
            create("upload") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = rootProject.file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    flavorDimensions += "env"
    productFlavors {
        // ما يُرفع للمتجر. لا يُوقَّع إلا بمفتاح الرفع، أو لا يُبنى.
        create("production") {
            dimension = "env"
            manifestPlaceholders["appLabel"] = "فَلاح"
        }
        // ما يُجرَّب على الأجهزة. **معرِّفٌ مختلفٌ ولاحقةٌ في الاسم** — فلا
        // يلتبس بالإنتاج، ويمكن تثبيتُ الاثنين معًا على جهازٍ واحد.
        create("staging") {
            dimension = "env"
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            // الاسمُ الظاهرُ تحت الأيقونة يقول إنه تجريبيّ — لا يُعرف الفرقُ
            // من المعرِّف وحدَه، والمستخدمُ يرى الاسمَ لا المعرِّف.
            manifestPlaceholders["appLabel"] = "فَلاح (تجريبيّ)"
        }
    }

    buildTypes {
        release {
            // لا يُمَسُّ التصغيرُ ولا حذفُ الموارد هنا: مكوّنُ Flutter يضبطهما
            // معًا، وتغييرُ أحدهما وحدَه يُسقط البناءَ برسالةٍ عن الآخر.
            // التوقيعُ يُسنَد لكلِّ منفذٍ على حدة أدناه — لا هنا. ولو أُسند
            // هنا لَسرى على المنفذين معًا، وهو بعينه ما نمنعه.
            signingConfig = null
        }
    }
}

// ── إسنادُ التوقيع لكلِّ منفذٍ على حدة ──
// يجري بعد أن يُنشئ المكوّنُ الإضافيُّ متغيّراتِ البناء، فيُعرف المنفذُ ونوعُه.
androidComponents {
    onVariants { variant ->
        if (variant.buildType == "release") {
            when (variant.flavorName) {
                "staging" -> variant.signingConfig
                    .setConfig(android.signingConfigs.getByName("debug"))
                "production" -> if (hasUploadKey) {
                    variant.signingConfig
                        .setConfig(android.signingConfigs.getByName("upload"))
                }
                // production بلا مفتاح: يبقى بلا توقيع، ويُوقفه الحارسُ أدناه
            }
        }
    }
}

// ── الحارس: نسخةُ إنتاجٍ بلا مفتاحٍ لا تُبنى أصلًا ──
// يُفحص عند الإعداد لا عند التوقيع: يفشل في ثانيةٍ برسالةٍ مفهومةٍ بدل أن
// يُنفق البناءُ دقائقَ ثم يُخرج ملفًّا لا يصلح.
gradle.taskGraph.whenReady {
    val wantsProductionRelease = gradle.startParameter.taskNames.any {
        val t = it.lowercase()
        t.contains("productionrelease") ||
            // `flutter build` يمرّر أحيانًا المهمّةَ بلا اسم المنفذ
            ((t.contains("assemblerelease") || t.contains("bundlerelease")) &&
                !t.contains("staging"))
    }
    if (wantsProductionRelease && !hasUploadKey) {
        throw GradleException(
            """

            ══════════════════════════════════════════════════════════
            ✗ لا يمكن بناءُ نسخةِ إنتاجٍ بلا مفتاح رفع.
            ══════════════════════════════════════════════════════════

            `android/key.properties` غيرُ موجود.

            وهذا ليس عائقًا يُلتفّ عليه: حزمةٌ موقَّعةٌ بمفتاح التصحيح
            يرفضها Google Play، ولو قَبِلها لَكان أسوأ — إذ يصير مفتاحُ
            تطبيقك مفتاحًا يملكه كلُّ من ثبَّت Android Studio.

            ┌─ للتجربة على جهازك الآن (لا يحتاج مفتاحًا) ─────────────
            │  flutter build apk --flavor staging --release
            │  ← معرِّفُه com.falah.app.staging واسمُه «فَلاح (تجريبيّ)»
            └────────────────────────────────────────────────────────

            ┌─ للمتجر ───────────────────────────────────────────────
            │  ولّد مفتاحَ رفعٍ ثم:
            │  flutter build appbundle --flavor production --release
            └────────────────────────────────────────────────────────

            الخطواتُ كاملةً — بما فيها التوليدُ من هاتفٍ بلا حاسوب،
            والتوقيعُ في GitHub Actions من الأسرار:

                docs/RELEASE_SIGNING.md

            """.trimIndent()
        )
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
