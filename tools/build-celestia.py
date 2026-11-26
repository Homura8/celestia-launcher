#!/usr/bin/env python3
"""Build and install a local Celestia development bundle on Apple Silicon."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".celestia"
VERSION = "0.1.0"
APP_NAME = "Celestia Launcher.app"

def fail(message):
    raise RuntimeError(message)

def run(args, env=None, capture=False, check=True):
    args = [str(x) for x in args]
    print("+", " ".join(args), flush=True)
    result = subprocess.run(args, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE if capture else None)
    if capture and result.stdout:
        print(result.stdout, end="", flush=True)
    if check and result.returncode:
        fail("Command failed (exit %d): %s" % (result.returncode, args[0]))
    return result

def require_directory(path):
    if path.is_symlink():
        fail("Refusing symlinked build/data directory: " + str(path))
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        fail("Not a directory: " + str(path))

def locate_xcode(env):
    candidates = []
    if env.get("DEVELOPER_DIR"):
        candidates.append(Path(env["DEVELOPER_DIR"]))
    selected = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True)
    if selected.returncode == 0:
        candidates.append(Path(selected.stdout.strip()))
    candidates += sorted(Path("/Applications").glob("Xcode*.app"), reverse=True)
    for path in candidates:
        if path.suffix == ".app":
            path = path / "Contents/Developer"
        probe = dict(env, DEVELOPER_DIR=str(path))
        if subprocess.run(["xcrun", "-sdk", "macosx", "metal", "--version"],
                          env=probe, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            return path
    fail("No working Metal compiler. Install Xcode's MetalToolchain component "
         "with xcodebuild -downloadComponent MetalToolchain and retry.")

def locate_java(env):
    candidates = [Path(env["JAVA_HOME"])] if env.get("JAVA_HOME") else []
    result = subprocess.run(["/usr/libexec/java_home", "-v", "25"],
                            capture_output=True, text=True)
    if result.returncode == 0:
        candidates.append(Path(result.stdout.strip()))
    candidates += [Path("/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home")]
    for path in candidates:
        if not (path / "bin/javac").is_file():
            continue
        result = subprocess.run([str(path / "bin/java"), "-version"],
                                capture_output=True, text=True)
        if result.returncode == 0 and '"25' in result.stderr:
            return path
    fail("JDK 25 is required. Install it (brew install openjdk@25) or set JAVA_HOME.")

def setup(args):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        fail("v0.1 builds on native Apple Silicon macOS only (not Rosetta).")
    env = os.environ.copy()
    env["PATH"] = str(Path.home() / ".cargo/bin") + ":/opt/homebrew/bin:/opt/homebrew/opt/rustup/bin:" + env.get("PATH", "")
    for tool in ("git", "rustup", "codesign", "plutil", "xcrun", "ditto"):
        if not shutil.which(tool, path=env["PATH"]):
            fail("Missing " + tool + ". Install rustup (brew install rustup) and Xcode first.")
    env["DEVELOPER_DIR"] = str(locate_xcode(env))
    env.pop("SDKROOT", None)
    env["JAVA_HOME"] = str(locate_java(env))
    env["PATH"] = str(Path(env["JAVA_HOME"]) / "bin") + ":" + env["PATH"]
    pin = (ROOT / "tools/ci/rust-version").read_text().strip()
    game_version = json.loads((ROOT / "research-lock.json").read_text())["minecraft"]["version"]
    prism = Path(args.prism).expanduser().resolve()
    if not prism.is_dir():
        fail("Prism directory not found: " + str(prism))
    server = Path(args.server_jar).expanduser().resolve()
    print("Xcode:", env["DEVELOPER_DIR"], "\nJava:", env["JAVA_HOME"],
          "\nRust pin:", pin, "\nMinecraft:", game_version, "\nPrism:", prism, flush=True)
    if args.check:
        return
    if run(["git", "status", "--porcelain", "--untracked-files=no"], capture=True).stdout.strip():
        fail("Tracked files are modified. Commit or stash your own changes first; "
             "the engine packager snapshots the committed checkout.")
    for path in (BASE, BASE / "build", BASE / "data", BASE / "data/launcher", BASE / "data/game"):
        require_directory(path)
    env["HORIZON_LAUNCHER_HOME"] = str(BASE / "data/launcher")
    env["HORIZON_HOME"] = str(BASE / "data/game")
    env["HORIZON_LAUNCHER_LOCATION_FILE"] = str(BASE / "data/location.json")
    env["HORIZON_LAUNCHER_NO_SELF_UPDATE"] = "1"
    env["HORIZON_TELEMETRY_URL"] = "off"
    env.pop("HORIZON_MSA_CLIENT_ID", None)
    # Keep the default build caches private to this checkout. Existing local builds
    # can be reused explicitly, without deleting or moving them.
    if not args.reuse_existing:
        for key, path in (("CARGO_HOME", BASE / "build/cargo"),
                          ("RUSTUP_HOME", BASE / "build/rustup")):
            require_directory(path)
            env[key] = str(path)
    engine_target = ROOT / "target" if args.reuse_existing else BASE / "build/engine"
    launcher_target = ROOT / "launcher/target" if args.reuse_existing else BASE / "build/launcher"
    if args.clean:
        for path in (engine_target, launcher_target):
            if path.is_symlink():
                fail("Refusing to clean symlink: " + str(path))
            if path.exists():
                shutil.rmtree(path)
    for path in (engine_target, launcher_target):
        require_directory(path)
    # Install the exact compiler and wasm components locally; no global rustup default change.
    run(["rustup", "toolchain", "install", pin, "--profile", "minimal",
         "--component", "rust-src", "--target", "wasm32-unknown-unknown"], env)
    rust_bin = Path(run(["rustup", "which", "--toolchain", pin, "cargo"], env, capture=True).stdout.strip()).parent
    env["PATH"] = str(rust_bin) + ":" + env["PATH"]
    env["RUSTUP_TOOLCHAIN"] = pin
    engine_env = dict(env, CARGO_TARGET_DIR=str(engine_target))
    launcher_env = dict(env, CARGO_TARGET_DIR=str(launcher_target))
    cargo = rust_bin / "cargo"
    release = engine_target / "release"
    run([cargo, "build", "--locked", "--release", "-p", "horizon-game",
         "-p", "horizon-client-lib", "-p", "horizon-prepare", "-p", "horizon-server",
         "--bin", "horizon-client", "--bin", "horizon-ctl", "--bin", "horizon-prepare",
         "--bin", "horizon-server"], engine_env)
    run([cargo, "run", "--locked", "-p", "cargo-horizon-mod", "--", "wasm-std",
         release / "horizon-wasm-std.wasm"], engine_env)
    prep = release / "horizon-prepare"
    prepare_args = [prep, "--prepare", "--complete", "--root", ROOT, "--prism-dir", prism]
    if server.is_file():
        prepare_args += ["--server-jar", server]
    # The explicit --prepare imports/validates artifacts even when --complete is set.
    run(prepare_args, engine_env)
    run([prep, "--check", "--root", ROOT], engine_env)
    result = run([prep, "compile-exporters", "--root", ROOT], engine_env, capture=True)
    shipped = ROOT / "exporters"
    candidates = [Path(line.strip()) for line in result.stdout.splitlines()
                  if line.strip().startswith(str(ROOT) + "/")]
    bundles = [p for p in candidates if p.is_dir() and (p / "manifest.json").is_file()
               and (p / "server").is_dir() and (p / "client").is_dir()]
    if not bundles:
        fail("Exporter compiler did not report a complete bundle path.")
    bundle = bundles[-1]
    if bundle.resolve() != shipped.resolve():
        if shipped.is_symlink():
            fail("Refusing to replace symlinked exporters directory.")
        with tempfile.TemporaryDirectory(dir=BASE / "build") as temp:
            staged = Path(temp) / "exporters"
            shutil.copytree(bundle, staged)
            if shipped.exists():
                shutil.rmtree(shipped)
            shutil.move(staged, shipped)
    run([cargo, "build", "--locked", "--release", "--manifest-path", "launcher/Cargo.toml"], launcher_env)
    launcher = launcher_target / "release/horizon-launcher"
    result = run([launcher, "--json", "developer-install", ROOT, "--program",
                  release / "horizon-client", "--trust-unsigned"], engine_env, capture=True)
    # The packager can print ordinary progress before the final JSON object.
    tag = None
    for i, char in enumerate(result.stdout):
        if char == "{":
            try:
                obj, _ = json.JSONDecoder().raw_decode(result.stdout[i:])
                if isinstance(obj, dict) and isinstance(obj.get("version"), str):
                    tag = obj["version"]
            except ValueError:
                pass
    if not tag or not tag.startswith("developer-") or len(tag) != 74 or any(c not in "0123456789abcdef" for c in tag[10:]):
        fail("Could not identify the installed developer build.")
    version_dir = BASE / "data/launcher/versions" / tag
    if not (version_dir / ".installed").is_file():
        fail("Developer installation marker not found.")
    # Import only verified prepared resources, never publish them in the app or git.
    resources = ROOT / ".local/horizon-client" / game_version
    dest = version_dir / ".local/horizon-client" / game_version
    if run([version_dir / "horizon-prepare", "--check", "--root", version_dir],
           engine_env, check=False).returncode:
        require_directory(dest.parent)
        with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
            staged = Path(temp) / game_version
            shutil.copytree(resources, staged)
            if dest.exists():
                if dest.is_symlink():
                    fail("Refusing to replace symlinked resources.")
                shutil.rmtree(dest)
            shutil.move(staged, dest)
    run([version_dir / "horizon-prepare", "--check", "--root", version_dir], engine_env)
    run([launcher, "settings", "install-new-versions", "off"], engine_env)
    run([launcher, "settings", "prune-old-versions", "off"], engine_env)
    run([launcher, "settings", "selected-version", tag], engine_env)
    package_app(launcher, env)
    print("\nReady:", BASE / APP_NAME, "\nOpen this app in Finder or run:\n  open \"" +
          str(BASE / APP_NAME) + "\"", flush=True)

WRAPPER = """#!/bin/bash
set -e
HERE="$(cd "$(dirname "$0")" && pwd -P)"
BASE="$(cd "$HERE/../../.." && pwd -P)"
export HORIZON_LAUNCHER_HOME="$BASE/data/launcher"
export HORIZON_HOME="$BASE/data/game"
export HORIZON_LAUNCHER_LOCATION_FILE="$BASE/data/location.json"
export HORIZON_LAUNCHER_NO_SELF_UPDATE=1
export HORIZON_TELEMETRY_URL=off
unset HORIZON_MSA_CLIENT_ID HORIZON_LAUNCHER_DEVELOPER_OFFLINE
if [ -s "$BASE/client-id" ]; then
    HORIZON_MSA_CLIENT_ID="$(cat "$BASE/client-id")"
    export HORIZON_MSA_CLIENT_ID
fi
if [ -f "$BASE/developer-mode" ]; then
    export HORIZON_LAUNCHER_DEVELOPER_OFFLINE=1
fi
exec "$HERE/horizon-launcher" "$@"
"""

def package_app(launcher, env):
    # Adapt the original macOS release plist and icon, without requiring dmgbuild
    # or the original team's signing identity. v0.1 is a local app, not a release DMG.
    with tempfile.TemporaryDirectory(dir=BASE) as temp:
        app = Path(temp) / APP_NAME
        macos = app / "Contents/MacOS"
        resources = app / "Contents/Resources"
        macos.mkdir(parents=True)
        resources.mkdir()
        shutil.copy2(launcher, macos / "horizon-launcher")
        wrapper = macos / "celestia-launcher"
        wrapper.write_text(WRAPPER)
        wrapper.chmod(0o755)
        shutil.copy2(ROOT / "packaging/icons/horizon.icns", resources / "horizon.icns")
        with (ROOT / "packaging/macos/Info.plist").open("rb") as f:
            plist = plistlib.load(f)
        plist.update(CFBundleDisplayName="Celestia Launcher",
                     CFBundleName="Celestia Launcher", CFBundleExecutable="celestia-launcher",
                     CFBundleIdentifier="io.github.homura8.celestia-launcher",
                     CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION)
        with (app / "Contents/Info.plist").open("wb") as f:
            plistlib.dump(plist, f)
        (app / "Contents/PkgInfo").write_text("APPL????")
        run(["plutil", "-lint", app / "Contents/Info.plist"], env)
        run(["codesign", "--force", "--sign", "-", macos / "horizon-launcher"], env)
        run(["codesign", "--force", "--sign", "-", app], env)
        run(["codesign", "--verify", "--deep", "--strict", app], env)
        # Preserve the previous app until the new one is verified.
        final = BASE / APP_NAME
        old = Path(temp) / "previous.app"
        if final.is_symlink():
            fail("Refusing to replace symlinked application.")
        if final.exists():
            final.rename(old)
        try:
            app.rename(final)
            run([final / "Contents/MacOS/celestia-launcher", "--version"], env)
        except BaseException:
            if final.exists():
                shutil.rmtree(final)
            if old.exists():
                old.rename(final)
            raise
    # Default to the upstream's explicit local single-player development mode
    # until the owner opts into real Microsoft authentication.
    if not (BASE / "client-id").exists() and not (BASE / "developer-mode").exists():
        (BASE / "developer-mode").touch()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="preflight only; no build")
    p.add_argument("--reuse-existing", action="store_true", help="reuse checkout targets and normal Rust caches")
    p.add_argument("--clean", action="store_true", help="discard only Celestia's two isolated Cargo target directories")
    p.add_argument("--prism", default=str(Path.home() / "Library/Application Support/PrismLauncher"))
    p.add_argument("--server-jar", default=str(Path.home() / "Downloads/horizon-assets/server.jar"))
    args = p.parse_args()
    if args.clean and args.reuse_existing:
        p.error("--clean cannot be combined with --reuse-existing")
    try:
        setup(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print("Celestia:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
