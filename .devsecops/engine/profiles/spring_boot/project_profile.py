#!/usr/bin/env python3
"""Detecta un proyecto Spring Boot sin depender de nombres o rutas concretas."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


IGNORED_DIRECTORIES = {
    ".git",
    ".gradle",
    ".devsecops",
    ".security-engine",
    ".idea",
    ".mvn",
    ".vscode",
    "build",
    "node_modules",
    "reports",
    "security-fixtures",
    "target",
}
BUILD_FILES = {
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
}
SPRING_MARKERS = (
    "org.springframework.boot",
    "spring-boot-starter",
    "spring-boot-gradle-plugin",
)


class DetectionError(RuntimeError):
    """La estructura del repositorio no permite elegir el proyecto con seguridad."""


def is_ignored(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in IGNORED_DIRECTORIES for part in parts)


def is_spring_boot_build(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return any(marker in content for marker in SPRING_MARKERS)


def candidates(root: Path) -> list[Path]:
    detected: list[Path] = []
    for name in BUILD_FILES:
        for path in root.rglob(name):
            if not is_ignored(path, root) and is_spring_boot_build(path):
                detected.append(path)
    return sorted(detected, key=lambda item: (len(item.relative_to(root).parts), item.as_posix()))


def select_build_file(root: Path, project_path: str) -> Path:
    if project_path != "auto":
        selected_root = (root / project_path).resolve()
        try:
            selected_root.relative_to(root)
        except ValueError as error:
            raise DetectionError("La ruta del proyecto queda fuera del repositorio.") from error
        found = [selected_root / name for name in BUILD_FILES if (selected_root / name).is_file()]
        spring = [path for path in found if is_spring_boot_build(path)]
        if len(spring) != 1:
            raise DetectionError(
                f"No se ha encontrado un unico proyecto Spring Boot en {project_path}."
            )
        return spring[0]

    found = candidates(root)
    if not found:
        raise DetectionError("No se ha encontrado ningun proyecto Spring Boot Maven o Gradle.")

    root_candidates = [path for path in found if path.parent == root]
    if len(root_candidates) == 1:
        return root_candidates[0]
    if len(found) == 1:
        return found[0]

    locations = ", ".join(path.relative_to(root).as_posix() for path in found)
    raise DetectionError(
        "Se han encontrado varios proyectos Spring Boot. "
        f"Indica project_path para seleccionar uno: {locations}"
    )


def find_dockerfile(project_root: Path, configured: str) -> Path | None:
    if configured not in {"", "auto"}:
        candidate = (project_root / configured).resolve()
        try:
            candidate.relative_to(project_root)
        except ValueError as error:
            raise DetectionError("El Dockerfile queda fuera del proyecto seleccionado.") from error
        if not candidate.is_file():
            raise DetectionError(f"No existe el Dockerfile indicado: {configured}")
        return candidate

    direct = project_root / "Dockerfile"
    if direct.is_file():
        return direct
    found = [
        path for path in project_root.rglob("Dockerfile")
        if not is_ignored(path, project_root)
    ]
    return found[0] if len(found) == 1 else None


def detect_java_version(build_file: Path) -> str:
    content = build_file.read_text(encoding="utf-8", errors="ignore")
    patterns = (
        r"<java\.version>\s*([^<]+)\s*</java\.version>",
        r"<maven\.compiler\.release>\s*([^<]+)\s*</maven\.compiler\.release>",
        r"JavaLanguageVersion\.of\((\d+)\)",
        r"sourceCompatibility\s*=\s*(?:JavaVersion\.VERSION_)?['\"]?(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            value = match.group(1).strip().replace("VERSION_", "").replace("_", ".")
            return value.removeprefix("1.")
    return "17"


def cyclonedx_gradle_version(project_root: Path) -> str:
    """Elige una version compatible con el wrapper, si el proyecto lo incluye."""
    wrapper = project_root / "gradle/wrapper/gradle-wrapper.properties"
    if not wrapper.is_file():
        return "3.3.0"
    content = wrapper.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"gradle-(\d+)\.(\d+)(?:\.\d+)?-", content)
    if not match:
        return "3.3.0"
    version = (int(match.group(1)), int(match.group(2)))
    if version < (8, 0):
        return "1.10.0"
    if version < (8, 4):
        return "2.3.1"
    return "3.3.0"


def source_paths(project_root: Path) -> list[str]:
    paths = [
        path.relative_to(project_root).as_posix()
        for path in (project_root / "src/main/java", project_root / "src/main/kotlin")
        if path.is_dir()
    ]
    return paths or ["src"] if (project_root / "src").is_dir() else ["."]


def build_profile(repository_root: Path, project_path: str, dockerfile: str) -> dict[str, Any]:
    root = repository_root.resolve()
    build_file = select_build_file(root, project_path)
    project_root = build_file.parent
    container_file = find_dockerfile(project_root, dockerfile)
    build_system = BUILD_FILES[build_file.name]
    relative_root = project_root.relative_to(root).as_posix() or "."
    relative_build = build_file.relative_to(root).as_posix()
    relative_dockerfile = (
        container_file.relative_to(root).as_posix() if container_file else None
    )
    slug_source = os.getenv("GITHUB_REPOSITORY", root.name).split("/")[-1]
    slug = re.sub(r"[^a-z0-9_.-]+", "-", slug_source.lower()).strip("-._") or "spring-boot-app"

    return {
        "schemaVersion": "1.0",
        "projectRoot": relative_root,
        "buildSystem": build_system,
        "buildFile": relative_build,
        "javaVersion": detect_java_version(build_file),
        "cycloneDxGradleVersion": cyclonedx_gradle_version(project_root),
        "sourcePaths": source_paths(project_root),
        "dockerfile": relative_dockerfile,
        "dockerContext": relative_root,
        "containerScan": container_file is not None,
        "imageTag": f"{slug}:security-scan",
    }


def github_outputs(profile: dict[str, Any], output: Path) -> None:
    values = {
        "project_root": profile["projectRoot"],
        "build_system": profile["buildSystem"],
        "build_file": profile["buildFile"],
        "java_version": profile["javaVersion"],
        "cyclonedx_gradle_version": profile["cycloneDxGradleVersion"],
        "source_paths": " ".join(profile["sourcePaths"]),
        "dockerfile": profile["dockerfile"] or "",
        "docker_context": profile["dockerContext"],
        "container_scan": str(profile["containerScan"]).lower(),
        "image_tag": profile["imageTag"],
    }
    with output.open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--project-path", default="auto")
    parser.add_argument("--dockerfile", default="auto")
    parser.add_argument("--output", type=Path, default=Path("reports/project-profile.json"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    try:
        profile = build_profile(args.repository_root, args.project_path, args.dockerfile)
    except DetectionError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.github_output:
        github_outputs(profile, args.github_output)
    print(json.dumps(profile, ensure_ascii=False))


if __name__ == "__main__":
    main()
