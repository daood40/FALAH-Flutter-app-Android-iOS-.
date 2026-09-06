import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// ═══════════ مفتاحُ التوقيع ═══════════
// مفتاحُ الرفع يحكم كلَّ تحديثٍ لاحقٍ للتطبيق: من ملكه نشر باسمنا، ومن
// أضاعه لم يعد يستطيع تحديثَ تطبيقه في المتجر أبدًا. فلا يدخل المستودعَ
// ولا هذه المحادثة، وإنما يُقرأ من `android/key.properties` (خارج git).
//
// وما كان هنا قبلَ اليوم أخطرُ من نقص: `signingConfig = debug` مع تعليقٍ
// يقول «مؤقّتًا». فكان `flutter build appbundle` يُخرج حزمةً تبدو جاهزةً
// للمتجر وهي موقَّعةٌ بمفتاحِ تصحيحٍ يرفضه Play — عيبٌ لا يظهر إلا عند
// الرفع، بعد أن يكون صاحبُه ظنَّ نفسه انتهى.
//
// فالقاعدةُ الآن: **البناءُ يقول الحقيقةَ عن نفسه**. بلا مفتاحٍ حقيقيّ
// يُلحَق باسم النسخة `-debugsigned`، فيقرؤه من ينظر في الملفّ أو في شاشة
// «عن التطبيق» — ولا تُرفع حزمةٌ ظنًّا أنها موقَّعة.
val keystoreProperties = Properties()
val keystoreFile = rootProject.file("key.properties")
val hasUploadKey = keystoreFile.exists()
if (hasUploadKey) {
    keystoreFile.inputStream().use { keystoreProperties.load(it) }
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
        // لا يُنشَأ إلا إن وُجد المفتاحُ فعلًا: إعدادٌ فارغٌ يفشل عند البناء
        // برسالةٍ غامضةٍ عن ملفٍّ لا وجودَ له، والغموضُ عدوُّ من يبني وحده.
        if (hasUploadKey) {
            create("upload") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = keystoreProperties["storeFile"]?.let { file(it) }
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            if (hasUploadKey) {
                signingConfig = signingConfigs.getByName("upload")
            } else {
                // يبقى البناءُ ممكنًا ليُجرَّب على جهازٍ حقيقيّ — لكنّه
                // يُعلن عن نفسه. `-debugsigned` يظهر في اسم النسخة، وفي
                // `aapt dump badging`، وفي شاشة «عن التطبيق».
                signingConfig = signingConfigs.getByName("debug")
                versionNameSuffix = "-debugsigned"
            }
        }
    }
}

// تحذيرٌ عند الإعداد لا عند الرفع: من بنى حزمةً بلا مفتاحٍ يعرف الآن،
// لا بعد أن يرفضها المتجر.
if (!hasUploadKey) {
    logger.lifecycle(
        "\n⚠  لا مفتاحَ رفعٍ (android/key.properties مفقود).\n" +
        "   نسخةُ الإصدار ستُوقَّع بمفتاحِ التصحيح وتُوسَم -debugsigned،\n" +
        "   و Google Play يرفضها. راجع docs/RELEASE_SIGNING.md.\n"
    )
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
