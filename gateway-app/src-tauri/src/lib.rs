// lib.rs — Tauri 2.x 共享入口

use std::sync::{Arc, Mutex};
#[cfg(not(debug_assertions))]
use tauri::AppHandle;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::CommandChild;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::ShellExt;

type SharedSidecar = Arc<Mutex<Option<CommandChild>>>;

/// 强制杀掉整个进程树，避免子进程（或未来新增的孙进程）在主程序退出后残留。
///
/// 仅调用 `CommandChild::kill()` / `Child::kill()` 在正常情况下已经足够（Windows 上底层就是
/// `TerminateProcess`，无需目标进程配合），但为了绝对保证「关闭桌面端 = gateway 进程一定退出」，
/// 这里额外用系统命令做一次进程树级别的强杀，双重保险。
fn force_kill_tree(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }

    #[cfg(not(target_os = "windows"))]
    {
        // Unix：先礼貌地 kill 进程组，杀不掉再上 -9。
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .output();
        let _ = std::process::Command::new("kill")
            .args(["-KILL", &pid.to_string()])
            .output();
    }
}

// Release 模式：启动 PyInstaller 打包好的 gateway sidecar
#[cfg(not(debug_assertions))]
async fn spawn_sidecar(app: &AppHandle, shared: SharedSidecar) {
    let parent_pid = std::process::id().to_string();
    match app.shell().sidecar("gateway") {
        Ok(cmd) => match cmd.env("GATEWAY_PARENT_PID", parent_pid).spawn() {
            Ok((_rx, child)) => {
                println!("[Gateway] sidecar started pid={}", child.pid());
                *shared.lock().unwrap() = Some(child);
            }
            Err(e) => eprintln!("[Gateway] sidecar spawn failed: {e}"),
        },
        Err(e) => eprintln!("[Gateway] sidecar unavailable: {e}"),
    }
}

// Debug 模式：直接用本地 Python 启动 gateway/main.py
#[cfg(debug_assertions)]
fn spawn_python_dev(project_root: &str) -> Option<std::process::Child> {
    let script = format!("{project_root}/gateway/main.py");
    let python = find_python_dev();
    println!("[Gateway] dev mode: {python} {script}");
    let parent_pid = std::process::id().to_string();

    #[cfg(target_os = "windows")]
    let result = {
        use std::os::windows::process::CommandExt;
        std::process::Command::new(&python)
            .arg(&script)
            .current_dir(project_root)
            .env("GATEWAY_PARENT_PID", &parent_pid)
            .creation_flags(0x08000000)
            .spawn()
    };

    #[cfg(not(target_os = "windows"))]
    let result = std::process::Command::new(&python)
        .arg(&script)
        .current_dir(project_root)
        .env("GATEWAY_PARENT_PID", &parent_pid)
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

/// 关闭时统一清理所有已启动的子进程（sidecar / dev python）。
/// 可能会被 `RunEvent::ExitRequested` 和 `RunEvent::Exit` 重复调用，因此要保证幂等。
fn cleanup_children(
    shared_sidecar: &SharedSidecar,
    #[cfg(debug_assertions)] shared_dev: &SharedDevChild,
) {
    if let Ok(mut guard) = shared_sidecar.lock() {
        if let Some(child) = guard.take() {
            let pid = child.pid();
            let _ = child.kill();
            force_kill_tree(pid);
            println!("[Gateway] sidecar stopped (pid={pid})");
        }
    }

    #[cfg(debug_assertions)]
    if let Ok(mut guard) = shared_dev.lock() {
        if let Some(mut child) = guard.take() {
            let pid = child.id();
            let _ = child.kill();
            force_kill_tree(pid);
            println!("[Gateway] python stopped (pid={pid})");
        }
    }
}

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

            // 后台启动 gateway，不阻塞窗口显示
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
                    drop(app_handle);
                }
            });

            Ok(())
        })
        // 窗口被关闭时立即请求整个 App 退出，避免出现「窗口没了但进程/子进程还在」的中间态。
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                window.app_handle().exit(0);
            }
        });

    builder
        .build(tauri::generate_context!())
        .expect("failed to build tauri app")
        .run(move |_app, event| {
            // ExitRequested / Exit 都可能收到，cleanup 内部是幂等的（take() 后为 None 就不会重复杀进程）。
            match event {
                RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                    cleanup_children(
                        &shared_sidecar_for_run,
                        #[cfg(debug_assertions)]
                        &shared_dev_for_run,
                    );
                }
                _ => {}
            }
        });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    run_app();
}
