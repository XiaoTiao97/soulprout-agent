// Desktop binary entry point
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    soulprout_gateway_lib::run();
}
