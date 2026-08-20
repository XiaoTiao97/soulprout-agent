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

/// 停止 sidecar 并释放它对 `gateway-*.exe` 的文件占用。
///
/// 除了退出清理，安装更新前也必须调用：NSIS 安装包要覆盖安装目录下的 sidecar
/// 可执行文件，而 Windows 不允许覆盖正在运行的 exe，不先停掉安装会失败。
/// `take()` 之后再次调用即为空操作，因此是幂等的。
fn stop_sidecar(shared: &SharedSidecar) {
    if let Ok(mut guard) = shared.lock() {
        if let Some(child) = guard.take() {
            let pid = child.pid();
            let _ = child.kill();
            force_kill_tree(pid);
            println!("[Gateway] sidecar stopped (pid={pid})");
        }
    }
}

/// 关闭时统一清理所有已启动的子进程（sidecar / dev python）。
/// 可能会被 `RunEvent::ExitRequested` 和 `RunEvent::Exit` 重复调用，因此要保证幂等。
fn cleanup_children(
    shared_sidecar: &SharedSidecar,
    #[cfg(debug_assertions)] shared_dev: &SharedDevChild,
) {
    stop_sidecar(shared_sidecar);

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

/// 版本清单地址，发版脚本会往这个位置覆盖上传。
#[cfg(not(debug_assertions))]
const UPDATE_MANIFEST_URL: &str =
    "https://soulprout-gateway-app.oss-cn-hongkong.aliyuncs.com/updates/version.json";

/// 启动后延迟一会儿再查更新，先把窗口和 gateway 让给用户。
#[cfg(not(debug_assertions))]
const UPDATE_CHECK_DELAY_SECS: u64 = 3;

/// OSS 上 `version.json` 的内容，由 `scripts/release.ps1` 生成。
#[cfg(not(debug_assertions))]
#[derive(serde::Deserialize)]
struct RemoteVersion {
    version: String,
    #[serde(default)]
    notes: String,
    url: String,
}

#[cfg(not(debug_assertions))]
async fn fetch_manifest() -> Result<RemoteVersion, String> {
    // 附上时间戳，绕开 OSS/CDN 可能的缓存，避免发了新版却读到旧清单
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?
        .get(format!("{UPDATE_MANIFEST_URL}?t={nonce}"))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .json::<RemoteVersion>()
        .await
        .map_err(|e| e.to_string())
}

#[cfg(not(debug_assertions))]
async fn download_installer(url: &str, version: &str) -> Result<std::path::PathBuf, String> {
    let bytes = reqwest::Client::new()
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .bytes()
        .await
        .map_err(|e| e.to_string())?;

    let path = std::env::temp_dir().join(format!("Soulprout-Gateway-{version}-setup.exe"));
    std::fs::write(&path, &bytes).map_err(|e| e.to_string())?;
    Ok(path)
}

/// 检查更新：有新版本就询问用户，同意后下载安装并自动重启。
///
/// 任何一步失败都只记日志或提示，不影响 gateway 正常使用。
#[cfg(not(debug_assertions))]
async fn check_and_apply_update(app: AppHandle, sidecar: SharedSidecar) {
    use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};

    tokio::time::sleep(std::time::Duration::from_secs(UPDATE_CHECK_DELAY_SECS)).await;

    let remote = match fetch_manifest().await {
        Ok(remote) => remote,
        Err(e) => {
            eprintln!("[Updater] check failed: {e}");
            return;
        }
    };

    let latest = match semver::Version::parse(&remote.version) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("[Updater] bad version {:?}: {e}", remote.version);
            return;
        }
    };
    let current = app.package_info().version.clone();
    if latest <= current {
        println!("[Updater] already up to date ({current})");
        return;
    }

    let notes = remote.notes.trim();
    let detail = if notes.is_empty() {
        format!("发现新版本 {latest}（当前 {current}）")
    } else {
        format!("发现新版本 {latest}（当前 {current}）\n\n{notes}")
    };

    let accepted = app
        .dialog()
        .message(format!(
            "{detail}\n\n更新期间 Gateway 会短暂断开，安装完成后自动重启。"
        ))
        .title("Soulprout Gateway 有新版本")
        .buttons(MessageDialogButtons::OkCancelCustom(
            "立即更新".to_string(),
            "稍后再说".to_string(),
        ))
        .blocking_show();

    if !accepted {
        println!("[Updater] user postponed {latest}");
        return;
    }

    // 先下载，此时 gateway 仍在正常服务
    let installer = match download_installer(&remote.url, &remote.version).await {
        Ok(path) => path,
        Err(e) => {
            eprintln!("[Updater] download failed: {e}");
            app.dialog()
                .message(format!(
                    "下载更新失败：{e}\n\n可稍后重试，或前往官网手动下载最新版本。"
                ))
                .title("更新失败")
                .blocking_show();
            return;
        }
    };

    // 安装包要覆盖 sidecar 可执行文件，必须先释放占用
    stop_sidecar(&sidecar);

    // /P 静默带进度条，/R 装完自动启动新版本，/UPDATE 走升级模式（不卸载，保留 gateway_data）
    // 工作目录切到临时目录，避免安装器占用待覆盖的安装目录
    let spawned = std::process::Command::new(&installer)
        .args(["/P", "/R", "/UPDATE"])
        .current_dir(std::env::temp_dir())
        .spawn();

    match spawned {
        Ok(_) => {
            println!("[Updater] installer launched for {latest}, exiting");
            // 必须退出，安装器才能覆盖正在运行的主程序
            std::process::exit(0);
        }
        Err(e) => {
            eprintln!("[Updater] failed to launch installer: {e}");
            // 没能启动安装器，把刚才停掉的 gateway 拉回来，否则用户会面对一个空壳窗口
            spawn_sidecar(&app, sidecar).await;
            app.dialog()
                .message(format!(
                    "启动安装程序失败：{e}\n\n可前往官网手动下载最新版本。"
                ))
                .title("更新失败")
                .blocking_show();
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
        .plugin(tauri_plugin_dialog::init())
        .setup(move |app| {
            let app_handle = app.handle().clone();
            let sidecar_ref = shared_sidecar.clone();

            #[cfg(debug_assertions)]
            let dev_ref = shared_dev.clone();

            #[cfg(not(debug_assertions))]
            {
                let update_handle = app_handle.clone();
                let update_sidecar = shared_sidecar.clone();

                // 后台启动 gateway，不阻塞窗口显示
                tauri::async_runtime::spawn(async move {
                    spawn_sidecar(&app_handle, sidecar_ref).await;
                });

                tauri::async_runtime::spawn(check_and_apply_update(update_handle, update_sidecar));
            }

            #[cfg(debug_assertions)]
            std::thread::spawn(move || {
                let cwd = std::env::current_dir()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string();
                if let Some(child) = spawn_python_dev(&cwd) {
                    *dev_ref.lock().unwrap() = Some(child);
                }
                drop(sidecar_ref);
                drop(app_handle);
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
