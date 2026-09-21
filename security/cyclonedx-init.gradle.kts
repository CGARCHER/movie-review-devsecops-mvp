import org.cyclonedx.gradle.CyclonedxPlugin

val cyclonedxPluginVersion = System.getenv("CYCLONEDX_GRADLE_PLUGIN_VERSION") ?: "3.3.0"

initscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.cyclonedx.bom:org.cyclonedx.bom.gradle.plugin:$cyclonedxPluginVersion")
    }
}

rootProject {
    apply<CyclonedxPlugin>()
}
