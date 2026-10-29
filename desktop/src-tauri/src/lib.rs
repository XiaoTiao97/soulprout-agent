// lib.rs — Soulprout 桌面端 Tauri 外壳
//
// 外壳只做四件事：
//   1. 选一个本机空闲端口 + 生成一次性启动密钥；
//   2. 启动 Python sidecar（界面、本机工具、gateway 都在里面），把端口和密钥通过环境变量交给它；
//   3. 等 sidecar 起来后，把窗口从开屏页导航到 http://127.0.0.1:<port>/__boot?s=<密钥>；
//   4. 窗口关闭 / 应用退出时，把 sidecar 整个进程树结束掉。
//
// 登录令牌、本机文件操作都在 sidecar 里，外壳不接触。

use std::collections::hash_map::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{Manager, RunEvent};

/// 等 sidecar 就绪的最长时间。冷启动要加载 gateway 及一堆依赖，给足余量。
const READY_TIMEOUT_SECS: u64 = 90;

/// 已启动的 sidecar 进程号。release 与 debug 共用：退出时按进程树结束。
type SharedPid = Arc<Mutex<Option<u32>>>;

/// 强制结束整个进程树，避免窗口关了、Python 子进程（以及它启动的 bash 等）还留在后台。
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
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .output();
        let _ = std::process::Command::new("kill")
            .args(["-KILL", &pid.to_string()])
            .output();
    }
}

fn stop_sidecar(shared: &SharedPid) {
    if let Ok(mut guard) = shared.lock() {
        if let Some(pid) = guard.take() {
            force_kill_tree(pid);
            println!("[Desktop] sidecar stopped (pid={pid})");
        }
    }
}

/// 向系统要一个本机空闲端口。
fn pick_free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    Ok(listener.local_addr()?.port())
}

/// 一次性启动密钥：只有外壳和 sidecar 知道，页面请求必须带上它换取 Cookie。
/// `RandomState` 的哈希种子来自操作系统随机源，这里取 4 个拼成 256 位。
fn random_secret() -> String {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let mut out = String::with_capacity(64);
    for i in 0..4u64 {
        let mut hasher = RandomState::new().build_hasher();
        hasher.write_u64(i);
        hasher.write_u128(nanos);
        out.push_str(&format!("{:016x}", hasher.finish()));
    }
    out
}

/// release：启动 PyInstaller 打包好的 sidecar。
#[cfg(not(debug_assertions))]
fn spawn_sidecar(app: &tauri::AppHandle, port: u16, secret: &str) -> Result<u32, String> {
    use tauri_plugin_shell::process::CommandEvent;
    use tauri_plugin_shell::ShellExt;

    let command = app
        .shell()
        .sidecar("soulprout-desktop-sidecar")
        .map_err(|e| format!("找不到 sidecar：{e}"))?
        .env("SOULPROUT_DESKTOP_PORT", port.to_string())
        .env("SOULPROUT_DESKTOP_SECRET", secret)
        .env("SOULPROUT_PARENT_PID", std::process::id().to_string());
    let (mut rx, child) = command.spawn().map_err(|e| format!("启动 sidecar 失败：{e}"))?;
    let pid = child.pid();
    println!("[Desktop] sidecar started pid={pid} port={port}");

    // 把 sidecar 的输出读走并打印（管道没人读会写满后把它卡住）。child 句柄不能丢，丢了管道会被关掉。
    tauri::async_runtime::spawn(async move {
        let _child = child;
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    println!("[sidecar] {}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[Desktop] sidecar exited: {:?}", payload.code);
                    break;
                }
                _ => {}
            }
        }
    });
    Ok(pid)
}

/// debug：直接用本机 Python 跑 desktop/sidecar/main.py，界面用 desktop/ui/dist。
#[cfg(debug_assertions)]
fn spawn_sidecar(app: &tauri::AppHandle, port: u16, secret: &str) -> Result<u32, String> {
    let repo_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let script = repo_root.join("desktop").join("sidecar").join("main.py");
    let ui_dir = repo_root.join("desktop").join("ui").join("dist");
    let python = find_python_dev()?;
    println!("[Desktop] dev mode: {python} {}", script.display());

    let mut cmd = std::process::Command::new(&python);
    cmd.arg(&script)
        .current_dir(&repo_root)
        .env("SOULPROUT_DESKTOP_PORT", port.to_string())
        .env("SOULPROUT_DESKTOP_SECRET", secret)
        .env("SOULPROUT_PARENT_PID", std::process::id().to_string());
    // 默认连官网云服务。本地联调请在桌面端「设置 → 云端服务」里改地址，不要再用 AGENT_URL 锁死。
    if std::env::var("SOULPROUT_UI_DIR").is_err() {
        cmd.env("SOULPROUT_UI_DIR", &ui_dir);
    }

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }

    let mut child = cmd.spawn().map_err(|e| format!("启动 Python 失败（{python}）：{e}"))?;
    let pid = child.id();

    // sidecar 如果很快就退出了（缺依赖、脚本报错等），别让用户干等到超时
    let app = app.clone();
    std::thread::spawn(move || {
        if let Ok(status) = child.wait() {
            eprintln!("[Desktop] sidecar exited: {status}");
            if let Some(window) = app.get_webview_window("main") {
                let message = format!(
                    "本机服务已退出（{status}）。请在终端里查看错误输出，通常是 Python 缺依赖：pip install -r desktop/sidecar/requirements.txt"
                );
                let _ = window.eval(&format!(
                    "window.__spFail && window.__spFail('{}')",
                    js_string(&message)
                ));
            }
        }
    });
    Ok(pid)
}

/// debug：找一个能用的 Python。优先 SOULPROUT_PYTHON，其次当前 conda 环境，最后 PATH 里的。
/// 必须真的能 `import aiohttp`：Windows 的 WindowsApps\python.exe 只是个应用商店占位符，会被这一步筛掉。
#[cfg(debug_assertions)]
fn find_python_dev() -> Result<String, String> {
    let usable = |python: &str| {
        let mut probe = std::process::Command::new(python);
        probe.args(["-c", "import aiohttp"]);
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            probe.creation_flags(0x0800_0000);
        }
        probe.output().map(|o| o.status.success()).unwrap_or(false)
    };

    // 环境变量优先；其次是 desktop/.dev-python（单行路径，已加入 .gitignore，每个开发者各写各的）
    let from_file = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join(".dev-python"),
    )
    .ok()
    .map(|text| text.trim().to_string())
    .filter(|text| !text.is_empty());
    if let Some(explicit) = std::env::var("SOULPROUT_PYTHON").ok().or(from_file) {
        return if usable(&explicit) {
            Ok(explicit)
        } else {
            Err(format!("指定的 Python 不可用（需要能 import aiohttp）：{explicit}"))
        };
    }

    let mut candidates: Vec<String> = Vec::new();
    if let Ok(prefix) = std::env::var("CONDA_PREFIX") {
        let exe = std::path::Path::new(&prefix).join(if cfg!(windows) { "python.exe" } else { "bin/python" });
        candidates.push(exe.to_string_lossy().to_string());
    }
    candidates.extend(["python", "python3", "py"].iter().map(|s| s.to_string()));
    for candidate in candidates {
        if usable(&candidate) {
            return Ok(candidate);
        }
    }
    Err("找不到可用的 Python（需要已安装 desktop/sidecar/requirements.txt 的依赖）。请设置环境变量 SOULPROUT_PYTHON 指向解释器，例如 D:\\anaconda\\envs\\soulprout\\python.exe".to_string())
}

/// 等 sidecar 的 HTTP 端口能连上。
async fn wait_until_ready(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let deadline = std::time::Instant::now() + Duration::from_secs(READY_TIMEOUT_SECS);
    while std::time::Instant::now() < deadline {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok() {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(150)).await;
    }
    false
}

fn js_string(text: &str) -> String {
    // 作为 JS 字符串字面量嵌入 eval：只需要转义反斜杠、引号和换行
    text.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', "\\n")
        .replace('\r', "")
}

fn run_app() {
    let shared_pid: SharedPid = Arc::new(Mutex::new(None));
    let shared_for_setup = shared_pid.clone();
    let shared_for_run = shared_pid.clone();

    let builder = tauri::Builder::default()
        // 必须第一个注册：重复启动时只把已有窗口带到前台，不再另起一份 sidecar
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            let handle = app.handle().clone();
            let shared = shared_for_setup.clone();

            let port = pick_free_port().map_err(|e| format!("无法选择本机端口：{e}"))?;
            let secret = random_secret();

            match spawn_sidecar(&handle, port, &secret) {
                Ok(pid) => {
                    *shared.lock().unwrap() = Some(pid);
                }
                Err(message) => {
                    eprintln!("[Desktop] {message}");
                    // 开屏页可能还没加载完，稍等一下再把错误显示出来
                    tauri::async_runtime::spawn(async move {
                        tokio::time::sleep(Duration::from_millis(1200)).await;
                        if let Some(window) = handle.get_webview_window("main") {
                            let _ = window.eval(&format!(
                                "window.__spFail && window.__spFail('{}')",
                                js_string(&message)
                            ));
                        }
                    });
                    return Ok(());
                }
            }

            // 后台等待就绪，不阻塞窗口显示（窗口先显示开屏页）
            tauri::async_runtime::spawn(async move {
                let ready = wait_until_ready(port).await;
                let Some(window) = handle.get_webview_window("main") else {
                    return;
                };
                if ready {
                    let url = format!("http://127.0.0.1:{port}/__boot?s={secret}");
                    let _ = window.eval(&format!("window.location.replace('{}')", js_string(&url)));
                } else {
                    let _ = window.eval(
                        "window.__spFail && window.__spFail('本机服务启动超时，请关闭后重试。')",
                    );
                }
            });
            Ok(())
        })
        // 窗口被关闭时立即退出整个应用，避免「窗口没了但进程还在」
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                window.app_handle().exit(0);
            }
        });

    builder
        .build(tauri::generate_context!())
        .expect("failed to build tauri app")
        .run(move |_app, event| {
            // ExitRequested / Exit 都可能收到，stop_sidecar 是幂等的（take() 之后为空）
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                stop_sidecar(&shared_for_run);
            }
        });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    run_app();
}
