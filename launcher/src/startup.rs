use super::*;

// Windows' process-entry stack is only 1 MiB. Keep the entire launcher, including CLI
// dispatch, on an explicitly sized stack instead of constructing startup frames there.
// GPUI initializes OLE, creates windows and pumps their messages on this same thread:
// no COM or GUI state is constructed on the entry thread that waits for it.
// 16 MiB is a generous reserve, sixteen times the 1 MiB default that the startup regression
// test constrains the entry thread to; Windows commits a thread stack only as it grows.
#[cfg(windows)]
pub(super) fn run() {
    let launcher = std::thread::Builder::new()
        .name("launcher".into())
        .stack_size(16 * 1024 * 1024)
        .spawn(run_launcher)
        .unwrap_or_else(|error| {
            eprintln!(
                "{}",
                trf(
                    "Could not start the launcher: {error}",
                    &[("error", &error.to_string())],
                )
            );
            std::process::exit(1);
        });
    if let Err(payload) = launcher.join() {
        std::panic::resume_unwind(payload);
    }
}

// In particular, AppKit must stay on macOS's original main thread.
#[cfg(not(windows))]
pub(super) fn run() {
    run_launcher();
}

/// The bundled faces, which every window of the launcher's sets its text in.
pub(super) fn add_fonts(cx: &mut App) {
    cx.text_system()
        .add_fonts(vec![
            Cow::Borrowed(horizon_theme::fonts::GEIST_MONO),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_REGULAR),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_MEDIUM),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_SEMIBOLD),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_BOLD),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_DISPLAY_BOLD),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_DISPLAY_SEMIBOLD),
            Cow::Borrowed(horizon_theme::fonts::BRICOLAGE_HEADING_SEMIBOLD),
            Cow::Borrowed(horizon_theme::fonts::GEIST_REGULAR),
            Cow::Borrowed(horizon_theme::fonts::GEIST_MEDIUM),
            Cow::Borrowed(horizon_theme::fonts::GEIST_SEMIBOLD),
        ])
        .expect("bundled fonts");
}

// The locally packaged Celestia app keeps its instance data beside the app.
// A bare executable retains the original developer/CLI behavior.
#[cfg(target_os = "macos")]
fn celestia_environment() {
    use std::{env, fs, path::Path};
    fn app_root(exe: &Path) -> Option<&Path> {
        let macos = exe.parent()?;
        let contents = macos.parent()?;
        let app = contents.parent()?;
        if macos.file_name()?.to_str()? != "MacOS"
            || contents.file_name()?.to_str()? != "Contents"
            || app.file_name()?.to_str()? != "Celestia Launcher.app"
        {
            return None;
        }
        app.parent()
    }

    let Ok(exe) = env::current_exe() else { return };
    let Some(base) = app_root(&exe) else { return };
    let data = base.join("data");
    if !data.join("launcher").is_dir() || !data.join("game").is_dir() {
        eprintln!("Celestia Launcher must stay beside its data directory. Move the enclosing folder, not the app alone.");
        std::process::exit(1);
    }
    // Called before the launcher starts any worker threads.
    env::set_var("HORIZON_LAUNCHER_HOME", data.join("launcher"));
    env::set_var("HORIZON_HOME", data.join("game"));
    env::set_var("HORIZON_LAUNCHER_LOCATION_FILE", data.join("location.json"));
    env::set_var("HORIZON_LAUNCHER_NO_SELF_UPDATE", "1");
    env::set_var("HORIZON_TELEMETRY_URL", "off");
    // Always override a built-in ID, even when the local configuration is absent.
    let id = fs::read_to_string(base.join("client-id")).unwrap_or_default();
    env::set_var("HORIZON_MSA_CLIENT_ID", id.trim());
    if base.join("developer-mode").is_file() {
        env::set_var("HORIZON_LAUNCHER_DEVELOPER_OFFLINE", "1");
    } else {
        env::remove_var("HORIZON_LAUNCHER_DEVELOPER_OFFLINE");
    }
}

fn run_launcher() {
    #[cfg(target_os = "macos")]
    celestia_environment();
    // First, before any other thread reads the environment.
    horizon_launcher::update_handoff::take_min_restarted_env();
    horizon_platform::mod_package::holder::retain_capability();
    if let Some(code) = native_mods::internals_rustc_wrapper() {
        std::process::exit(code);
    }
    if let Err(error) = console::attach_for_cli() {
        eprintln!(
            "{}",
            trf(
                "Could not restore the launcher's terminal streams: {error}",
                &[("error", &error.to_string())],
            )
        );
        std::process::exit(1);
    }
    // Windows setup: `setup --quiet` / `uninstall --quiet` run here without a window, and never
    // reach the CLI parser below (so neither the MCP tools nor the completions list them).
    #[cfg(windows)]
    if let Some(code) = horizon_launcher::installer::run_quiet() {
        std::process::exit(code);
    }
    if let Some(worker) = horizon_launcher::relocation::Worker::from_args() {
        let code = if worker.restarts() {
            move_window::run(worker)
        } else {
            worker.run_and_finish(|_| {}, &std::sync::atomic::AtomicBool::new(false))
        };
        std::process::exit(code);
    }
    // A broken location must still open a window: startup() falls back to the default
    // folders and records the error, which Settings shows with Retry and Use the default folder.
    // It keeps the migration lease for the life of the process.
    let _location_error = horizon_launcher::data_location::startup();
    perf::process_started();
    backend::exe_path();
    if let Some(code) = horizon_launcher::update_handoff::run() {
        std::process::exit(code);
    }
    #[cfg(windows)]
    backend::remove_replaced_binaries();
    backend::cleanup_launcher_updates();
    // What the launcher downloads goes through the player's proxy, if they set one: the parts
    // that build their own agents (`horizon-port-pack`) are told before anything starts.
    horizon_launcher::proxy::announce(horizon_launcher::backend::Settings::load().proxy);
    // The setup wizard and `horizon-launcher.exe uninstall` (what Control Panel runs) are windows,
    // not CLI commands: asked of the CLI parser first, `uninstall` was refused as an unknown
    // subcommand, with the error going to the console that Control Panel's start doesn't have.
    #[cfg(windows)]
    let setup_window = horizon_launcher::installer::window_mode();
    #[cfg(not(windows))]
    let setup_window: Option<horizon_launcher::setup_args::Mode> = None;
    if setup_window.is_none() {
        if let Some(code) = cli::run() {
            std::process::exit(code);
        }
    }
    // The GPU's texture limit, which caps the pictures made from disk (`picture_cache`).
    horizon_launcher::pictures::probe_gpu_limit();
    gpui_platform::application()
        .with_assets(blocks::Assets)
        // `move`: the closure owns `setup_window`; `run` wants it to outlive this frame.
        .run(move |cx: &mut App| {
            add_fonts(cx);
            cx.bind_keys(key_bindings());
            cx.on_action(|_: &Quit, cx| shut_down(cx));
            // The key press is being handled inside the window, so the window can only be
            // removed once that update has finished.
            cx.on_action(|_: &CloseWindow, cx| {
                cx.defer(|cx| {
                    for window in cx.windows() {
                        let _ = window.update(cx, |_, window, _| window.remove_window());
                    }
                })
            });
            cx.set_menus(menus());
            // The setup exe (and `horizon-launcher.exe uninstall`) opens its own window instead.
            #[cfg(windows)]
            if let Some(mode) = setup_window {
                setup_page::open(mode, cx);
                return;
            }
            #[cfg(not(windows))]
            let _ = setup_window;
            let bounds = Bounds::centered(None, size(px(1180.), px(760.)), cx);
            cx.open_window(
                WindowOptions {
                    window_bounds: Some(WindowBounds::Windowed(bounds)),
                    window_min_size: Some(size(px(960.), px(600.))),
                    titlebar: Some(titlebar::options()),
                    #[cfg(target_os = "linux")]
                    window_decorations: Some(gpui::WindowDecorations::Client),
                    app_id: Some("horizon-launcher".into()),
                    // GPUI draws a window without focus at most every 33 ms to save energy. A
                    // benchmark's window often starts without it (KDE keeps focus from windows
                    // a background process opens), and it measures drawing, not that limit.
                    inactive_frame_interval: if perf::Bench::wanted() {
                        None
                    } else {
                        WindowOptions::default().inactive_frame_interval
                    },
                    ..Default::default()
                },
                |window, cx| cx.new(|cx| crate::window_root::Shell::new(window, cx)),
            )
            .expect("window");
            cx.on_window_closed(|cx, _| shut_down(cx)).detach();
            cx.activate(true);
        });
}
