# Celestia Launcher

An independent Minecraft launcher project built around Horizon's Rust client, with Apple Silicon as the first development target.

Celestia started as a personal experiment to see how well Minecraft could run natively on a Mac without the JVM running the game. After building Horizon from source, I wanted a simpler way to manage the native client, its settings and future builds without going back to the terminal every time.

This repository is the starting point for that work. It contains a fork of [Horizon](https://github.com/horizon-rust/horizon), including its native game engine and desktop launcher. The engine is the work of the Horizon developers; Celestia is a separate project built on top of it, not a new implementation of Minecraft from scratch.

## Current status

Celestia is in early development. The inherited Horizon client and launcher have been compiled locally on an Apple Silicon MacBook Pro with an M1 Pro. The native client runs, renders worlds through Metal, and has been tested with shaders, HDR and the built-in graphics benchmark. Resource preparation from an existing Prism Launcher installation has also been tested.

The desktop launcher opens successfully, but Celestia's own Microsoft sign-in and authenticated multiplayer are not working yet. A Microsoft application has been registered for Celestia Launcher and a request for Minecraft API access was submitted to Mojang on 26 November 2026. Approval is pending.

There are no Celestia release builds at the moment. The UI and much of the functionality in this checkout are still inherited from Horizon.

## What I want to build

- A native desktop launcher with its own design and straightforward instance management.
- A reproducible, one-command build that keeps toolchains, build caches and generated files inside a dedicated project directory where practical.
- Local engine installation, version selection and rollback without relying on the original Horizon release repository.
- Better integration with existing Prism installations, without modifying their worlds or settings.
- Graphics profiling, shader experiments and performance tuning for Apple Silicon, with measurements rather than advertised FPS targets.
- A way to review, test and incorporate useful changes from other Horizon forks and contributors while keeping Celestia's own changes separate.

The initial focus is macOS. Support for other platforms and conventional Java Edition instances can be explored once the native launcher is reliable.

## Minecraft accounts and game files

Celestia is intended for players who own Minecraft: Java Edition. It is not a way to obtain the game for free or bypass ownership checks.

The planned sign-in flow uses Microsoft's device authorization flow through Celestia's own application registration. Minecraft API access is needed to verify ownership, retrieve the signed-in player's profile and establish authenticated sessions for multiplayer. Celestia will not reuse Horizon's application ID or the ID of another launcher.

The inherited launcher implements local credential storage, using the operating system's credential store where supported (including macOS Keychain). The intended design is to keep credentials on the user's device and not pass access tokens in command-line arguments. Authentication and privacy behaviour will be reviewed before any public release. See the existing [authentication implementation](docs/microsoft-account.md) and [forking notes](docs/forking.md) for the current code's design.

Game resources are prepared locally from the player's own Minecraft installation. The resource preparer checks the required game files against the pinned checksums. Celestia does not intend to distribute Mojang's game jars, extracted assets, prepared resource bundles or account credentials. Do not commit any of these to this repository.

## Building from source

The instructions below are for the current macOS development checkout, not a finished Celestia installer.

### Requirements

- A Mac with Apple Silicon for the tested configuration.
- A recent Rust toolchain (the workspace requires Rust 1.95 or later; some development tools require the exact version in [`tools/ci/rust-version`](tools/ci/rust-version)).
- JDK 25, with `JAVA_HOME` pointing to the JDK.
- Xcode with the Metal compiler available (`xcrun -sdk macosx metal --version`). The standalone Command Line Tools may not be sufficient for building the GUI.
- Your own installation of Minecraft: Java Edition 26.3 and the matching server JAR from Mojang.

### Celestia v0.1 build

A local macOS build entry point is now available:

```sh
./Build.command --check
./Build.command
```

For an existing checkout, `./Build.command --reuse-existing` reuses the previous Cargo build directories. See the [v0.1 build guide](docs/celestia-build.md) for prerequisites, configuration, output and limitations. This is a development build, not a public release.

### Native client

```sh
git clone --depth 1 https://github.com/Homura8/horizon-mc.git
cd horizon-mc
```

For Prism Launcher on macOS, install and run the pinned Minecraft version first, then prepare its resources using the matching server JAR:

```sh
cargo run --release -p horizon-prepare -- \
  --prepare --complete \
  --prism-dir "$HOME/Library/Application Support/PrismLauncher" \
  --server-jar /path/to/server.jar

cargo run --release -p horizon-game
```

Replace `/path/to/server.jar` with the path to your own matching 26.3 server JAR. Prepared resources remain local to the checkout. Back up any important worlds before testing development builds.

### Desktop launcher

```sh
cargo build --release --manifest-path launcher/Cargo.toml
./launcher/target/release/horizon-launcher
```

The GUI currently uses the inherited Horizon design. Opening it does not automatically install the locally built engine; that requires the companion binaries, exporter bundle and developer installation step. See the [launcher documentation](launcher/README.md) and [developer installation implementation](launcher/src/developer_install.rs). Microsoft sign-in is not available for Celestia until its application has the necessary approval.

## Development

Most of the code in this repository is still Horizon's. Its original documentation is retained as a reference for the engine, and may describe upstream services or releases that are unavailable to this fork.

| Path | Purpose |
| --- | --- |
| [`launcher/`](launcher/) | Rust/GPUI desktop launcher |
| [`crates/horizon-game/`](crates/horizon-game/) | Native game executable |
| [`crates/horizon-prepare/`](crates/horizon-prepare/) | Local resource preparation |
| [`packaging/macos/`](packaging/macos/) | macOS application packaging |
| [`docs/`](docs/) | Inherited technical documentation |

Useful references: [native client build guide](docs/native-client.md), [Launch API](docs/api/launch.md), [engine architecture](docs/layers.md) and [forking guide](docs/forking.md).

Bug reports and contributions are welcome through this repository. For engine changes from another fork, please include the source commit and retain its authorship so that the changes can be reviewed and tested.

## Credits and licence

Horizon was founded by [Ludovic Marie](https://github.com/ludovic111) and developed by the Horizon team, including [Kacper](https://github.com/kacpherek), [Cosmic](https://github.com/Online5277), [levzzz](https://github.com/levzzz5154), [rdbt](https://github.com/rdbtCVS), [Anthony S](https://github.com/dezer-x), [Nikita](https://github.com/NikitaMGrimm) and its many other contributors. Celestia's starting point is their work, and the original Git history is retained.

The [original Horizon README](https://github.com/Homura8/horizon-mc/blob/ae632edf48f6cae3ba52a5c81523ec712488c9cc/README.md) is available in this repository's history.

Horizon's original work is licensed under the [GNU LGPL v3 or later](LICENSE). Earlier code released under the [MIT licence](LICENSES/MIT.txt) retains that licence. Third-party dependencies retain their respective licences; see the [third-party notices](THIRD_PARTY_NOTICES.md). Celestia's modifications to the inherited code remain subject to the applicable licences.

Celestia Launcher is maintained independently by [Homura8](https://github.com/Homura8). It is not an official continuation of Horizon and is not affiliated with its original team.

**NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT.** Minecraft is a trademark of Mojang Synergies AB. Use of the game remains subject to the [Minecraft EULA](https://www.minecraft.net/en-us/eula).
