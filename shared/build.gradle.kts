plugins {
    kotlin("multiplatform")
    id("com.android.library")
}
kotlin {
    androidTarget()
    jvm()
    iosArm64()
    iosSimulatorArm64()
    targets.withType<org.jetbrains.kotlin.gradle.plugin.mpp.KotlinNativeTarget>().configureEach {
        binaries.framework { baseName = "Shared"; isStatic = true }
    }
    sourceSets { commonTest.dependencies { implementation(kotlin("test")) } }
}
android {
    namespace = "app.circleguard.shared"
    compileSdk = 35
    defaultConfig { minSdk = 26 }
}
