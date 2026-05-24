// Soulprout Gateway — Tauri 桌面外壳
//
// 职责：
//   1. 启动 Python gateway 后端
//      - Release 构建：通过 Tauri Sidecar 运行打包好的 gateway.exe（用户无需装 Python）
//      - Debug  构建：直接调用 `python gateway/main.py`（开发调试用）
//   2. 等待后端 HTTP 服务就绪（http://localhost:8082）
//   3. 打开 Tauri webview 加载管理界面
//   4. 应用退出时终止后端进程
//
// 微信接入参考：https://github.com/NousResearch/hermes-agent

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

type SharedSidecar = Arc<Mutex<Option<CommandChild>>>;

// ── 等待后端就绪 ────────────────────────────────────────────────

fn wait_for_backend(url: &str, max_secs: u64) -> bool {
    let deadline = std::time::Instant::now() + Duration::from_secs(max_secs);
    while std::time::Instant::now() < deadline {
        // 用标准库 TcpStream 探测端口是否开放（不依赖 HTTP 库）
        let port = 8082u16;
        if std::net::TcpStream::connect(format!("127.0.0.1:{}", port)).is_ok() {
            // 端口开放后再等一下，让 FastAPI 完成路由注册
            std::thread::sleep(Duration::from_millis(800));
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    eprintln!("[Gateway] 等待后端就绪超时（{}s）", max_secs);
    false
}

// ── Release 构建：Tauri Sidecar（内嵌 gateway.exe）─────────────

#[cfg(not(debug_assertions))]
async fn spawn_sidecar(app: &AppHandle, shared: SharedSidecar) {
    match app.shell().sidecar("gateway") {
        Ok(cmd) => {
            match cmd.spawn() {
                Ok((_rx, child)) => {
                    println!("[Gateway] Sidecar 已启动");
                    *shared.lock().unwrap() = Some(child);
                }
                Err(e) => eprintln!("[Gateway] Sidecar spawn 失败: {}", e),
            }
        }
        Err(e) => eprintln!("[Gateway] 获取 sidecar 失败: {}", e),
    }
}

// ── Debug 构建：直接调用 python（开发模式）──────────────────────

#[cfg(debug_assertions)]
fn spawn_python_dev(project_root: &str) -> Option<std::process::Child> {
    let script = format!("{}/gateway/main.py", project_root);
    let python = find_python_dev();
    println!("[Gateway] Dev 模式：{} {}", python, script);

    #[cfg(target_os = "windows")]
    let result = std::process::Command::new(&python)
        .arg(&script)
        .current_dir(project_root)
        .creation_flags(0x08000000) // CREATE_NO_WINDOW
        .spawn();

    #[cfg(not(target_os = "windows"))]
    let result = std::process::Command::new(&python)
        .arg(&script)
        .current_dir(project_root)
        .spawn();

    match result {
        Ok(child) => {
            println!("[Gateway] Python pid={}", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[Gateway] 启动 Python 失败: {}", e);
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

// ── 共享的 Dev 子进程（仅 debug 构建使用）──────────────────────
#[cfg(debug_assertions)]
type SharedDevChild = Arc<Mutex<Option<std::process::Child>>>;

// ── Tauri App 构建入口 ──────────────────────────────────────────

pub fn run_app() {
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

            // 在后台线程启动后端进程并等待就绪
            std::thread::spawn(move || {
                // ── Release：用 Sidecar ──
                #[cfg(not(debug_assertions))]
                {
                    let rt = tokio::runtime::Runtime::new().unwrap();
                    rt.block_on(spawn_sidecar(&app_handle, sidecar_ref));
                }

                // ── Debug：用 python 命令 ──
                #[cfg(debug_assertions)]
                {
                    let cwd = std::env::current_dir()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    if let Some(child) = spawn_python_dev(&cwd) {
                        *dev_ref.lock().unwrap() = Some(child);
                    }
                    drop(sidecar_ref); // 消耗掉以避免 unused 警告
                }

                // 等待 FastAPI 就绪后显示窗口
                wait_for_backend("http://localhost:8082", 40);

                if let Some(win) = app_handle.get_webview_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            });

            Ok(())
        });

    builder
        .build(tauri::generate_context!())
        .expect("Tauri 构建失败")
        .run(move |_app, event| {
            if let RunEvent::Exit = event {
                // Release：终止 sidecar
                if let Ok(mut guard) = shared_sidecar_for_run.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                        println!("[Gateway] Sidecar 已终止");
                    }
                }

                // Debug：终止 python 子进程
                #[cfg(debug_assertions)]
                if let Ok(mut guard) = shared_dev_for_run.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        println!("[Gateway] Python 进程已终止");
                    }
                }
            }
        });
}

fn main() {
    run_app();
}
