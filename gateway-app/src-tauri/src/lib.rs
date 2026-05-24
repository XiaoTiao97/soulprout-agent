// lib.rs — 移动端 / 桌面端共享入口（Tauri 2.x 约定）
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    crate::run_app();
}
