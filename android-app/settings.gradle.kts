pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven ( "https://dl.bintray.com/google/webrtc/")
        maven ("https://jitpack.io")
    }
}

rootProject.name = "injest"
include(":app")
 