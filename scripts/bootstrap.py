#!/usr/bin/env python3
"""Install build tools only inside this checkout. Requires Python 3 + curl + Xcode."""
import concurrent.futures
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.tools'
TOOLS.mkdir(exist_ok=True)

def download(url, name):
    path = TOOLS / name
    if not path.exists():
        subprocess.run(['curl', '-fL', '--retry', '3', '-o', str(path) + '.part', url], check=True)
        Path(str(path) + '.part').rename(path)
    return path

def java():
    if (TOOLS / 'jdk/Contents/Home/bin/java').exists():
        return
    arch = 'aarch64' if platform.machine() == 'arm64' else 'x64'
    archive = download(f'https://api.adoptium.net/v3/binary/latest/17/ga/mac/{arch}/jdk/hotspot/normal/eclipse', 'jdk.tar.gz')
    dest = TOOLS / 'jdk-unpack'
    dest.mkdir(exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(dest, filter='data')
    next(dest.iterdir()).rename(TOOLS / 'jdk')
    shutil.rmtree(dest)

def gradle():
    if (TOOLS / 'gradle-8.11.1/bin/gradle').exists():
        return
    archive = download('https://services.gradle.org/distributions/gradle-8.11.1-bin.zip', 'gradle.zip')
    with zipfile.ZipFile(archive) as z:
        z.extractall(TOOLS)
    (TOOLS / 'gradle-8.11.1/bin/gradle').chmod(0o755)

def android():
    dest = TOOLS / 'android-sdk/cmdline-tools/latest'
    if dest.exists():
        return
    archive = download('https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip', 'android-cli.zip')
    unpack = TOOLS / 'android-unpack'
    with zipfile.ZipFile(archive) as z:
        z.extractall(unpack)
    dest.parent.mkdir(parents=True, exist_ok=True)
    (unpack / 'cmdline-tools').rename(dest)
    shutil.rmtree(unpack)
    for f in (dest / 'bin').iterdir():
        f.chmod(0o755)

with concurrent.futures.ThreadPoolExecutor() as pool:
    list(pool.map(lambda fn: fn(), [java, gradle, android]))

env = os.environ | {
    'JAVA_HOME': str(TOOLS / 'jdk/Contents/Home'),
    'ANDROID_HOME': str(TOOLS / 'android-sdk'),
    'ANDROID_USER_HOME': str(TOOLS / 'android-user'),
    'GRADLE_USER_HOME': str(ROOT / '.gradle'),
    'KONAN_DATA_DIR': str(TOOLS / 'konan'),
}
sdk = TOOLS / 'android-sdk/cmdline-tools/latest/bin/sdkmanager'
subprocess.run([str(sdk), '--licenses'], input='y\n' * 100, text=True, env=env, check=True)
subprocess.run([str(sdk), 'platform-tools', 'platforms;android-35', 'build-tools;35.0.0'], env=env, check=True)
(ROOT / 'local.properties').write_text(f'sdk.dir={TOOLS / "android-sdk"}\n')
subprocess.run(['python3', '-m', 'venv', str(ROOT / '.venv')], check=True)
(ROOT / '.venv/pip.conf').write_text(f'[global]\ncache-dir = {TOOLS / "pip-cache"}\n')
print('Local tools ready. Run ./scripts/check.sh')
