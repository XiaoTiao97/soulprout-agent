; NSIS 安装/卸载钩子。
;
; 1. 安装前结束桌面端和 sidecar，避免覆盖正在运行的 exe 时出现
;    「无法打开要写入的文件」。
; 2. 把实际安装目录改成 %LOCALAPPDATA%\Soulprout。
;    productName 仍是「灵芽」（开始菜单 / 控制面板显示名不变），
;    但 NSIS 的 File 指令写 CJK 路径时会失败，所以目录必须是 ASCII。

!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /T /IM soulprout-desktop.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM soulprout-desktop-sidecar.exe'
  Pop $0
  Sleep 800
  StrCpy $INSTDIR "$LOCALAPPDATA\Soulprout"
  ; 旧版本（单文件 sidecar）把它放在安装目录根下；新版本是 sidecar\ 子目录。
  ; 先清掉旧文件和旧的 sidecar 目录，避免残留文件和新版本混在一起。
  Delete "$INSTDIR\soulprout-desktop-sidecar.exe"
  RMDir /r "$INSTDIR\sidecar"
  SetOutPath $INSTDIR
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; SetOutPath 可能先建过 %LOCALAPPDATA%\灵芽，空目录就清掉
  RMDir "$LOCALAPPDATA\${PRODUCTNAME}"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /T /IM soulprout-desktop.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM soulprout-desktop-sidecar.exe'
  Pop $0
  Sleep 800
!macroend
