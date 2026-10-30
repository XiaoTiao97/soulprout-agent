; NSIS 安装/卸载钩子（Tauri installerHooks）。
; - 安装/卸载前结束桌面端与 sidecar，避免 exe 被占用。
; - 安装目录固定为 %LOCALAPPDATA%\Soulprout（ASCII），避免 NSIS 写 CJK 路径失败。
;
; windows/nsis/installer.nsi 在 Tauri 默认模板上仅两处改动：
;   RequestExecutionLevel admin（浏览器下载的安装包需 UAC，否则易写文件失败）
;   .onInit / 升级卸载前调用 SoulproutKillProcesses

!macro SoulproutKillProcesses
  nsExec::Exec 'taskkill /F /T /IM soulprout-desktop.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM soulprout-desktop-sidecar.exe'
  Pop $0
  Sleep 1200
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro SoulproutKillProcesses
  StrCpy $INSTDIR "$LOCALAPPDATA\Soulprout"
  Delete "$INSTDIR\soulprout-desktop-sidecar.exe"
  RMDir /r "$INSTDIR\sidecar"
  SetOutPath $INSTDIR
!macroend

!macro NSIS_HOOK_POSTINSTALL
  RMDir "$LOCALAPPDATA\灵芽"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro SoulproutKillProcesses
!macroend
