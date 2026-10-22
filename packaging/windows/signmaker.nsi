; Sign Maker for SolidCraft - Windows x64 setup (NSIS 3)
; Same layout as Del's other installers (postmanpat-303/BigWaveRadio installer/bigwave.nsi).
; Built by packaging/pyinstaller.sh on the Windows runner, after PyInstaller:
;   makensis -DVERSION=1.0.1 -DVIVERSION=1.0.1.0 -DPKGDIR=..\..\dist\SignMaker
;            -DOUTFILE=..\out\SignMaker-1.0.1-setup-x64.exe packaging\windows\signmaker.nsi
; Bitmaps: tools/make_branding.py. Icon: assets/icon.ico (tools/make_icons.py).
; Silent install: SignMaker-<ver>-setup-x64.exe /S   (desktop shortcut included by default)
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef VIVERSION
  !define VIVERSION "${VERSION}.0"
!endif
!ifndef PKGDIR
  !define PKGDIR "..\..\dist\SignMaker"
!endif
!ifndef OUTFILE
  !define OUTFILE "..\out\SignMaker-${VERSION}-setup-x64.exe"
!endif

!define APPNAME "Sign Maker"
!define FULLNAME "Sign Maker for SolidCraft"
!define EXE "SignMaker.exe"
!define PUBLISHER "Del (postmanpat)"
!define REGKEY "Software\SignMakerForSolidCraft"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\SignMakerForSolidCraft"
!define ICON "..\..\assets\icon.ico"
!define REPOURL "https://github.com/postmanpat-303/SignMaker-for-SolidCraft"
!define SOLIDCRAFTURL "https://github.com/tangency-labs/solidcraft/releases"

Name "${FULLNAME} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "${REGKEY}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
BrandingText "${FULLNAME} ${VERSION}"

VIProductVersion "${VIVERSION}"
VIAddVersionKey "ProductName" "${FULLNAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${FULLNAME} setup"
VIAddVersionKey "LegalCopyright" "MIT, (c) 2026 Del (postmanpat)"
VIAddVersionKey "CompanyName" "${PUBLISHER}"

!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_WELCOMEFINISHPAGE_BITMAP "welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "welcome.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "header.bmp"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TEXT "This will install ${FULLNAME} ${VERSION} on your computer.$\r$\n$\r$\nType your wording, pick a font, preview it, and export a two-colour 3MF sign ready to print.$\r$\n$\r$\nSign Maker is an unofficial community add-on. It needs SolidCraft, which is installed separately.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_TITLE "Sign Maker is installed"
!define MUI_FINISHPAGE_TEXT "${FULLNAME} has been installed.$\r$\n$\r$\nSolidCraft is not included. Install a SolidCraft build that includes solidcraft-cli before making signs. Sign Maker finds it automatically, or you can point it at solidcraft-cli.exe in the app."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Start Sign Maker"
!define MUI_FINISHPAGE_LINK "Get SolidCraft (separate download)"
!define MUI_FINISHPAGE_LINK_LOCATION "${SOLIDCRAFTURL}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PKGDIR}\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Close a running Sign Maker first, or its files can't be replaced.
!macro CLOSE_RUNNING UN
; Leaves 1 in $0 when a SignMaker.exe process exists, else 0.
; Toolhelp snapshot via the System plugin (32-bit PROCESSENTRY32W = 556 bytes).
Function ${UN}IsRunning
  StrCpy $0 0
  System::Call 'kernel32::CreateToolhelp32Snapshot(i 2, i 0) p .r4'
  ${If} $4 P<> -1
    System::Call '*(i 556, &l552) p .r5'
    System::Call 'kernel32::Process32FirstW(p r4, p r5) i .r6'
    ${DoWhile} $6 <> 0
      System::Call '*$5(i, i, i, i, i, i, i, i, i, &w260 .r7)'
      ${If} $7 == "${EXE}"
        StrCpy $0 1
        ${ExitDo}
      ${EndIf}
      System::Call 'kernel32::Process32NextW(p r4, p r5) i .r6'
    ${Loop}
    System::Free $5
    System::Call 'kernel32::CloseHandle(p r4)'
  ${EndIf}
FunctionEnd

Function ${UN}CloseRunning
  Call ${UN}IsRunning
  ${If} $0 == 1
    MessageBox MB_OKCANCEL|MB_ICONINFORMATION "Sign Maker is running. It will be closed to continue." /SD IDOK IDOK +2
    Abort
    nsExec::Exec 'taskkill /F /IM "${EXE}"'
    Pop $0
    StrCpy $2 0
    ${Do}
      Sleep 300
      Call ${UN}IsRunning
      IntOp $2 $2 + 1
      ${If} $2 >= 20
        ${ExitDo}
      ${EndIf}
    ${LoopUntil} $0 == 0
    Sleep 500
  ${EndIf}
FunctionEnd
!macroend
!insertmacro CLOSE_RUNNING ""
!insertmacro CLOSE_RUNNING "un."

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Sign Maker needs 64-bit Windows." /SD IDOK
    Abort
  ${EndIf}
  SetRegView 64
  Call CloseRunning
FunctionEnd

Function un.onInit
  SetRegView 64
  Call un.CloseRunning
FunctionEnd

!macro REFRESH_SHELL_ICONS
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend

Section "Sign Maker (required)" SecCore
  SectionIn RO
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ; An upgrade replaces the whole PyInstaller runtime folder.
  RMDir /r "$INSTDIR\_internal"
  File "${PKGDIR}\${EXE}"
  File /r "${PKGDIR}\_internal"
  File "${PKGDIR}\README.txt"
  File "${PKGDIR}\LICENSE.txt"
  File "/oname=signmaker.ico" "${ICON}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\signmaker.ico" 0

  WriteRegStr HKLM "${REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName" "${FULLNAME}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\${EXE},0"
  WriteRegStr HKLM "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "URLInfoAbout" "${REPOURL}"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoRepair" 1
  !insertmacro REFRESH_SHELL_ICONS
SectionEnd

Section "Desktop shortcut" SecDesktop
  SetShellVarContext all
  Delete "$DESKTOP\${APPNAME}.lnk"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  !insertmacro REFRESH_SHELL_ICONS
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "The app, its licence, Start Menu shortcuts and the uninstaller."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Put a Sign Maker shortcut on the desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  SetShellVarContext all
  Delete "$DESKTOP\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$INSTDIR\${EXE}"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\signmaker.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "${UNINSTKEY}"
  DeleteRegKey HKLM "${REGKEY}"
  !insertmacro REFRESH_SHELL_ICONS
  ; Settings (%APPDATA%\SignMaker) and saved signs (Documents\Sign Maker) are left alone.
SectionEnd
