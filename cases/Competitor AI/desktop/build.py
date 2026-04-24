"""Скрипт сборки desktop-релизов через PyInstaller."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

PROJECT_NAME = "Competitor AI"
MACOS_APP_NAME = "Competitor AI"
WINDOWS_EXE_NAME = "Competitor AI"
ENTRYPOINT_SERVER = "backend/run.py"
ENTRYPOINT_DESKTOP = "desktop/main.py"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
RELEASE_DIR = PROJECT_ROOT / "release"


def _profile_name(raw: str | None) -> str:
    """Определяет профиль сборки по аргументу и ОС.

    Args:
        raw: Пользовательский профиль из CLI.

    Returns:
        Имя профиля (`macos`, `windows` или `linux`).
    """
    if raw:
        return raw.lower().strip()
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _target_binary_name(profile: str) -> str:
    """Возвращает имя целевого бинарника для профиля.

    Args:
        profile: Имя профиля сборки.

    Returns:
        Имя итогового артефакта без расширения.
    """
    if profile == "macos":
        return MACOS_APP_NAME
    if profile == "windows":
        return WINDOWS_EXE_NAME
    return f"{PROJECT_NAME}-{profile}"


def _python_for_build() -> str:
    """Выбирает интерпретатор Python для сборки.

    Returns:
        Путь к python из `venv`, либо текущий `sys.executable`.
    """
    # Предпочитаем интерпретатор из локального venv для изоляции зависимостей сборки.
    if os.name == "nt":
        venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    else:
        venv_python = PROJECT_ROOT / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _desktop_icon_for_profile(profile: str) -> str | None:
    """Ищет подходящую иконку для целевого профиля.

    Args:
        profile: Имя профиля сборки.

    Returns:
        Путь к найденной иконке или `None`.
    """
    base = PROJECT_ROOT / "frontend"
    candidates: list[Path]
    if profile == "windows":
        candidates = [base / "brand-icon.ico"]
    elif profile == "macos":
        candidates = [base / "brand-icon.icns", base / "brand-icon.ico"]
    else:
        candidates = [base / "brand-icon.ico"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _build(profile: str, clean: bool) -> Path:
    """Собирает релизный артефакт выбранного профиля.

    Args:
        profile: Имя профиля сборки.
        clean: Признак очистки кеша PyInstaller.

    Returns:
        Путь к собранному артефакту.

    Raises:
        RuntimeError: При попытке кросс-компиляции или блокировке файла.
    """
    if profile == "windows" and os.name != "nt":
        raise RuntimeError(
            "Профиль windows можно собирать только на Windows (PyInstaller не поддерживает кросс-компиляцию)."
        )
    if profile == "macos" and sys.platform != "darwin":
        raise RuntimeError(
            "Профиль macos можно собирать только на macOS (PyInstaller не поддерживает кросс-компиляцию)."
        )

    target_name = _target_binary_name(profile)
    entrypoint = ENTRYPOINT_DESKTOP if profile in {"macos", "windows"} else ENTRYPOINT_SERVER

    # На macOS сборка через spec-файл стабильнее формирует .app bundle.
    python_executable = _python_for_build()

    if profile == "macos":
        spec_path = PROJECT_ROOT / "desktop" / f"{target_name}.spec"
        command = [python_executable, "-m", "PyInstaller", "--noconfirm"]
        if clean:
            command.append("--clean")
        if spec_path.exists():
            command.append(str(spec_path))
        else:
            command.extend(["--name", target_name, entrypoint, "--windowed"])
    else:
        command = [python_executable, "-m", "PyInstaller", "--noconfirm", "--name", target_name, entrypoint]
        if clean:
            command.insert(3, "--clean")
        command.extend(["--onefile"])
        if profile == "windows":
            # Для Windows собираем desktop-бинарник без консольного окна.
            command.append("--windowed")

    # Разделитель в --add-data зависит от ОС хоста, где запускается PyInstaller.
    data_sep = ";" if os.name == "nt" else ":"
    if profile in {"macos", "windows"}:
        use_embedded_desktop_assets = not (
            profile == "macos" and (PROJECT_ROOT / "desktop" / f"{target_name}.spec").exists()
        )
    else:
        use_embedded_desktop_assets = False

    if use_embedded_desktop_assets:
        # Десктоп-клиент использует загрузчик конфигурации проекта и может читать .env.
        command.extend(["--add-data", f".env{data_sep}."])
        if (PROJECT_ROOT / "frontend" / "brand-icon.png").exists():
            command.extend(["--add-data", f"frontend/brand-icon.png{data_sep}."])
        icon_path = _desktop_icon_for_profile(profile)
        if icon_path:
            command.extend(["--icon", icon_path])
    elif profile not in {"macos", "windows"}:
        # Серверному бандлу нужны статические файлы для web-режима.
        command.extend(
            [
                "--add-data",
                f"frontend{data_sep}frontend",
                "--add-data",
                f"data{data_sep}data",
            ]
        )

    if profile == "windows":
        target_exe = DIST_DIR / f"{target_name}.exe"
        if target_exe.exists():
            try:
                target_exe.unlink()
            except PermissionError as exc:
                raise RuntimeError(
                    f"Не удалось перезаписать {target_exe}: файл занят другим процессом. "
                    "Закройте приложение и повторите сборку."
                ) from exc

    print("Running:", " ".join(command))
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)
    artifact = DIST_DIR / target_name
    if profile == "macos":
        # Для macOS поставляем только .app bundle.
        stale_binary = DIST_DIR / f"{PROJECT_NAME}-macos"
        if stale_binary.exists():
            stale_binary.unlink()
        artifact = DIST_DIR / f"{MACOS_APP_NAME}.app"
    if profile == "windows":
        artifact = artifact.with_suffix(".exe")
    return artifact


def _write_manifest(profile: str, artifact: Path) -> Path:
    """Формирует JSON-манифест собранного релиза.

    Args:
        profile: Имя профиля сборки.
        artifact: Путь к итоговому артефакту.

    Returns:
        Путь к созданному manifest-файлу.
    """
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "project": PROJECT_NAME,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "artifact_name": artifact.name,
        "artifact_path": str(artifact),
        "platform": {
            "os_name": os.name,
            "sys_platform": sys.platform,
            "python": sys.version.split()[0],
        },
    }
    manifest_path = RELEASE_DIR / f"{PROJECT_NAME}-{profile}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    """Разбирает аргументы и запускает процесс сборки."""
    parser = argparse.ArgumentParser(description="Build release artifact with OS profile.")
    parser.add_argument(
        "--profile",
        choices=["macos", "windows", "linux"],
        default=None,
        help="Target profile name. Default: current OS.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean PyInstaller cache before build.",
    )
    args = parser.parse_args()

    try:
        profile = _profile_name(args.profile)
        artifact = _build(profile=profile, clean=args.clean)
        manifest_path = _write_manifest(profile=profile, artifact=artifact)
        print(f"Build complete. Profile: {profile}. Artifact: {artifact}")
        print(f"Manifest saved: {manifest_path}")
    except RuntimeError as exc:
        print(f"\033[91mRuntimeError: {exc}\033[0m")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
