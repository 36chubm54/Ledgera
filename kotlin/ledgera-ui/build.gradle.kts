import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.testing.Test
import org.jetbrains.compose.desktop.application.dsl.TargetFormat
import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.compose)
    alias(libs.plugins.compose.compiler)
}

kotlin {
    jvmToolchain(21)
    jvm("desktop")

    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation(compose.runtime)
                implementation(compose.foundation)
                implementation(compose.animation)
                implementation(compose.material3)
                implementation(compose.components.resources)
                implementation(libs.kotlinx.coroutines.core)
            }
        }
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
            }
        }
        val desktopTest by getting {
            dependencies {
                implementation(kotlin("test-junit5"))
            }
        }
        val desktopMain by getting {
            kotlin.srcDir(layout.buildDirectory.dir("generated/uniffi/kotlin"))
            dependencies {
                implementation(compose.desktop.currentOs)
                implementation(libs.kotlinx.coroutines.swing)
                implementation(libs.jna)
                implementation(libs.jna.platform)
            }
        }
    }
}

val rustManifest = rootProject.layout.projectDirectory.file("rust/ledgera_engine/Cargo.toml")
val rustLibraryDir = rootProject.layout.projectDirectory.dir("rust/ledgera_engine/target/release")
val rustWorkspaceDir = rootProject.layout.projectDirectory.dir("rust/ledgera_engine")
val rustInputs = rootProject.fileTree(rustWorkspaceDir) {
    include("Cargo.lock")
    include("Cargo.toml")
    include("**/Cargo.toml")
    include("**/build.rs")
    include("**/src/**")
    include("**/uniffi.toml")
    exclude("target/**")
}
val hostOs = System.getProperty("os.name").lowercase()
val nativeLibraryName = when {
    hostOs.contains("win") -> "ledgera_engine.dll"
    hostOs.contains("mac") -> "libledgera_engine.dylib"
    else -> "libledgera_engine.so"
}
val uniffiBindgenName = if (hostOs.contains("win")) {
    "uniffi-bindgen.exe"
} else {
    "uniffi-bindgen"
}
val uniffiOutDir = layout.buildDirectory.dir("generated/uniffi/kotlin")
val uniffiDefinition = rootProject.layout.projectDirectory.file("rust/ledgera_engine/kotlin_ffi/src/ledgera_engine.udl")
val uniffiConfig = rootProject.layout.projectDirectory.file("rust/ledgera_engine/kotlin_ffi/uniffi.toml")
val skikoDataDir = rootProject.layout.projectDirectory.dir(".gradle/skiko")

val buildRustKotlinFfi by tasks.registering(Exec::class) {
    workingDir = rootProject.layout.projectDirectory.asFile
    inputs.files(rustInputs)
    outputs.files(
        rustLibraryDir.file(nativeLibraryName),
        rustLibraryDir.file(uniffiBindgenName),
    )
    commandLine(
        "cargo",
        "build",
        "--release",
        "--manifest-path",
        rustManifest.asFile.absolutePath,
        "-p",
        "ledgera_engine_kotlin_ffi",
    )
}

val generateUniffiKotlin by tasks.registering(Exec::class) {
    dependsOn(buildRustKotlinFfi)
    workingDir = rootProject.layout.projectDirectory.asFile
    inputs.files(uniffiDefinition, uniffiConfig)
    outputs.dir(uniffiOutDir)
    commandLine(
        rustLibraryDir.file(uniffiBindgenName).asFile.absolutePath,
        "generate",
        uniffiDefinition.asFile.absolutePath,
        "--language",
        "kotlin",
        "--out-dir",
        uniffiOutDir.get().asFile.absolutePath,
        "--config",
        uniffiConfig.asFile.absolutePath,
    )
}

tasks.withType<KotlinCompile>().configureEach {
    dependsOn(generateUniffiKotlin)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.named<Test>("desktopTest") {
    val testCompilation = kotlin.targets["desktop"].compilations["test"]
    val desktopTestClasses = layout.buildDirectory.dir("classes/kotlin/desktop/test")
    val testOutputs = testCompilation.output.allOutputs
    testClassesDirs = files(desktopTestClasses)
    classpath = files(desktopTestClasses) + testOutputs + (testCompilation.runtimeDependencyFiles ?: files())
    setScanForTestClasses(false)
    include("**/*Test.class")
}

tasks.named("desktopProcessResources", Copy::class) {
    dependsOn(buildRustKotlinFfi)
    from(rustLibraryDir) {
        include("ledgera_engine.dll", "libledgera_engine.so", "libledgera_engine.dylib")
        into("native")
    }
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("-Dskiko.data.path=${skikoDataDir.asFile.absolutePath}")
    if (name == "desktopRun") {
        mainClass.set("app.ledgera.MainKt")
    }
}

compose.resources {
    packageOfResClass = "app.ledgera.resources"
}

compose.desktop {
    application {
        mainClass = "app.ledgera.MainKt"
        nativeDistributions {
            targetFormats(TargetFormat.Dmg, TargetFormat.Msi, TargetFormat.Deb)
            packageName = "Ledgera"
            packageVersion = "3.0.0"
        }
    }
}
