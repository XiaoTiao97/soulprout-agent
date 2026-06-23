// lib.rs — Tauri 2.x 共享入口（桌面 + 移动端）

use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

type SharedSidecar = Arc<Mutex<Option<CommandChild>>>;

fn wait_for_backend(max_secs: u64) -> bool {
    let deadline = std::time::Instant::now() + Duration::from_secs(max_secs);
    while std::time::Instant::now() < deadline {
        let port = 8082u16;
        if std::net::TcpStream::connect(format!("127.0.0.1:{port}")).is_ok() {
            std::thread::sleep(Duration::from_millis(800));
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    eprintln!("[Gateway] backend not ready after {max_secs}s");
    false
}

#[cfg(not(debug_assertions))]
async fn spawn_sidecar(app: &AppHandle, shared: SharedSidecar) {
    match app.shell().sidecar("gateway") {
        Ok(cmd) => match cmd.spawn() {
            Ok((_rx, child)) => {
                println!("[Gateway] sidecar started");
                *shared.lock().unwrap() = Some(child);
            }
            Err(e) => eprintln!("[Gateway] sidecar spawn failed: {e}"),
        },
        Err(e) => eprintln!("[Gateway] sidecar unavailable: {e}"),
    }
}

#[cfg(debug_assertions)]
fn spawn_python_dev(project_root: &str) -> Option<std::process::Child> {
    let script = format!("{project_root}/gateway/main.py");
    let python = find_python_dev();
    println!("[Gateway] dev mode: {python} {script}");

    #[cfg(target_os = "windows")]
    let result = std::process::Command::new(&python)
        .arg(&script)
        .current_dir(project_root)
        .creation_flags(0x08000000)
        .spawn();

    #[cfg(not(target_os = "windows"))]
    let result = std::process::Command::new(&python)
        .arg(&script)
        .current_dir(project_root)
        .spawn();

    match result {
        Ok(child) => {
            println!("[Gateway] python pid={}", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[Gateway] failed to start python: {e}");
            None
        }
    }
}

#[cfg(debug_assertions)]
fn find_python_dev() -> String {
    for candidate in &["python", "python3", "py"] {
        if std::process::Command::new(candidate)
            .arg("--version")
            .output()
            .is_ok()
        {
            return candidate.to_string();
        }
    }
    "python".to_string()
}

#[cfg(debug_assertions)]
type SharedDevChild = Arc<Mutex<Option<std::process::Child>>>;

fn run_app() {
    let shared_sidecar: SharedSidecar = Arc::new(Mutex::new(None));
    let shared_sidecar_for_run = shared_sidecar.clone();

    #[cfg(debug_assertions)]
    let shared_dev: SharedDevChild = Arc::new(Mutex::new(None));
    #[cfg(debug_assertions)]
    let shared_dev_for_run = shared_dev.clone();

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            let app_handle = app.handle().clone();
            let sidecar_ref = shared_sidecar.clone();

            #[cfg(debug_assertions)]
            let dev_ref = shared_dev.clone();

            std::thread::spawn(move || {
                #[cfg(not(debug_assertions))]
                {
                    let rt = tokio::runtime::Runtime::new().unwrap();
                    rt.block_on(spawn_sidecar(&app_handle, sidecar_ref));
                }

                #[cfg(debug_assertions)]
                {
                    let cwd = std::env::current_dir()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    if let Some(child) = spawn_python_dev(&cwd) {
                        *dev_ref.lock().unwrap() = Some(child);
                    }
                    drop(sidecar_ref);
                }

                wait_for_backend(40);

                if let Some(win) = app_handle.get_webview_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            });

            Ok(())
        });

    builder
        .build(tauri::generate_context!())
        .expect("failed to build tauri app")
        .run(move |_app, event| {
            if let RunEvent::Exit = event {
                if let Ok(mut guard) = shared_sidecar_for_run.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                        println!("[Gateway] sidecar stopped");
                    }
                }

                #[cfg(debug_assertions)]
                if let Ok(mut guard) = shared_dev_for_run.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        println!("[Gateway] python stopped");
                    }
                }
            }
        });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    run_app();
}
