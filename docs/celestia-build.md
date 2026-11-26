# Celestia v0.1 — local macOS build

The build uses Horizon's existing native client, release packager, developer installation
mechanism and macOS bundle metadata. It does not download any upstream executable.

## Build

Install Xcode with its Metal toolchain, JDK 25, Python 3.9+ and rustup. Homebrew can
provide the latter three. Run Minecraft 26.3 in Prism once and have the matching
Mojang server JAR available. Close running Horizon/Celestia games and launchers before
building. Commit or stash any tracked edits first.

If the repository was originally cloned with --depth 1, explicitly fetch the branch:

    git remote set-branches --add origin celestia/v0.1
    git fetch origin
    git switch --track origin/celestia/v0.1

From the repository:

    ./Build.command --check
    ./Build.command

Or double-click Build.command in Finder. For an existing checkout like the original
development Mac, reuse the Cargo targets and normal Rust caches:

    ./Build.command --reuse-existing

This retains the native Cargo already on PATH. The WASM tool still uses the exact
upstream Rust pin through rustup.

Override paths if needed:

    ./Build.command --prism "/path/to/PrismLauncher" --server-jar "/path/to/server.jar"

The default server JAR is ~/Downloads/horizon-assets/server.jar. If no file is there,
the preparer may be able to use verified cached inputs or its Prism fallback. If
preparation fails, supply the correct server JAR explicitly.

## Output

    .celestia/
      Celestia Launcher.app
      build/           # isolated Rust toolchain, Cargo downloads and targets
      data/launcher/   # installed versions, launcher settings and metadata
      data/game/       # worlds, instances and game options
      developer-mode  # optional single-player developer mode marker
      client-id       # optional own Microsoft application client ID

The upstream preparer also writes ignored .local/ and exporters/ directories in the
checkout; the wasm builder may use target/horizon-mod. Xcode, JDK, Python, rustup and
Keychain remain system prerequisites. The generated app is ad-hoc signed, uses the
inherited icon and GUI for now, and must stay beside its data directory. Pin it to the
Dock instead of moving the app alone to Applications. No DMG or notarization is
produced in v0.1.

Existing Horizon and Prism saves are not migrated or modified. Back up worlds before
testing new engine builds. Re-running the build installs a new local developer version
and selects it for the currently selected Horizon instance in Celestia's own data.
Automatic installation and pruning of remote versions are disabled. Some inherited
online services and update checks may still report upstream errors.

For a clean compilation of the isolated Cargo targets:

    ./Build.command --clean

This preserves worlds, imported assets, cached downloads, installed versions and the
existing app until the replacement is ready. It never cleans the existing shared targets.

## Microsoft authentication

Until Mojang approves the new application, the app defaults to Horizon's explicit
single-player developer mode. This is not an ownership or multiplayer workaround.
Only use it to test your own locally built client with your own game files.

After approval, put your own registered client ID (a GUID) in .celestia/client-id and
remove .celestia/developer-mode. Restart the app and sign in normally. Do not use
another application's client ID. Do not commit credentials or Minecraft resources.

## Known limitations

The launcher still uses Horizon's internal executable name, UI and services. This
first version focuses on building and packaging, not a full rebrand. It is an
Apple Silicon development build, not a portable public installer.
