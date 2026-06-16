; ============================================================
; Transcrire Installer -- NSIS Script
; Targets: Windows 10/11 x64
; Bundles: Python 3.12, ffmpeg, app source, pre-built venv
; ============================================================

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; -- Metadata ------------------------------------------------------------------
Name              "Transcrire"
OutFile           "Transcrire-Setup.exe"
InstallDir        "$PROGRAMFILES64\Transcrire"
InstallDirRegKey  HKLM "Software\Transcrire" "InstallDir"
RequestExecutionLevel admin
SetCompressor     /SOLID lzma

; -- Version -------------------------------------------------------------------
!define APP_NAME    "Transcrire"
!define APP_VERSION "0.1.0"
!define APP_GUID    "{D4A2F3B1-9C7E-4E8A-A2D1-0F3C5B7E9D2A}"

; -- MUI Pages -----------------------------------------------------------------
!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
Page custom PageAPIKeys PageAPIKeysLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; -- API Key page variables ----------------------------------------------------
Var GroqKey
Var GeminiKey
Var APIKeysDialog
Var GroqField
Var GeminiField

; -- API Keys custom page ------------------------------------------------------
Function PageAPIKeys
    nsDialogs::Create 1018
    Pop $APIKeysDialog
    ${If} $APIKeysDialog == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 20u "Enter your API keys. These will be saved to a .env file in the install directory."
    Pop $0

    ${NSD_CreateLabel} 0 30u 100% 12u "Groq API Key:"
    Pop $0
    ${NSD_CreateText} 0 44u 100% 14u ""
    Pop $GroqField

    ${NSD_CreateLabel} 0 68u 100% 12u "Gemini API Key:"
    Pop $0
    ${NSD_CreateText} 0 82u 100% 14u ""
    Pop $GeminiField

    ${NSD_CreateLabel} 0 106u 100% 20u "Keys can be updated later by editing .env in your install folder."
    Pop $0

    nsDialogs::Show
FunctionEnd

Function PageAPIKeysLeave
    ${NSD_GetText} $GroqField $GroqKey
    ${NSD_GetText} $GeminiField $GeminiKey
FunctionEnd

; -- Integrity check helper ----------------------------------------------------
!macro CheckFileHash FILE EXPECTED_CRC
    VPatch::GetFileCRC32 "${FILE}"
    Pop $0
    ${If} $0 != "${EXPECTED_CRC}"
        MessageBox MB_ICONSTOP "Integrity check failed for ${FILE}.$\nThe installer may be corrupted. Please re-download."
        Abort
    ${EndIf}
!macroend

; -- Main install section ------------------------------------------------------
Section "Transcrire" SEC_MAIN
    SectionIn RO  ; required, cannot be deselected

    SetOutPath "$INSTDIR"

    ; -- Integrity checks -------------------------------------------------------
    DetailPrint "Verifying installer integrity..."
    !insertmacro CheckFileHash "$EXEDIR\files\ffmpeg.exe"  "04745F1E"
    !insertmacro CheckFileHash "$EXEDIR\files\ffprobe.exe" "04745F1E"

    ; -- ffmpeg ----------------------------------------------------------------
    DetailPrint "Installing ffmpeg..."
    CreateDirectory "$INSTDIR\bin"
    File "/oname=$INSTDIR\bin\ffmpeg.exe"  "files\ffmpeg.exe"
    File "/oname=$INSTDIR\bin\ffprobe.exe" "files\ffprobe.exe"

    ; Add ffmpeg to system PATH
    EnVar::SetHKLM
    EnVar::AddValue "PATH" "$INSTDIR\bin"

    ; -- App files -------------------------------------------------------------
    DetailPrint "Installing Transcrire..."
    File /r "..\domain"
    File /r "..\core"
    File /r "..\services"
    File /r "..\storage"
    File /r "..\cli"
    File /r "..\assets"
    File    "..\config.py"
    File    "..\pyproject.toml"

    ; -- Pre-built venv --------------------------------------------------------
    DetailPrint "Installing Python environment (no internet required)..."
    File /r "venv_dist"
    Rename "$INSTDIR\venv_dist" "$INSTDIR\.venv"

    ; Rewrite the venv's pyvenv.cfg to point to the new install location
    FileOpen $1 "$INSTDIR\.venv\pyvenv.cfg" w
    FileWrite $1 "home = $INSTDIR\.venv\Scripts$\r$\n"
    FileWrite $1 "include-system-site-packages = false$\r$\n"
    FileWrite $1 "version = 3.12$\r$\n"
    FileClose $1

    ; -- Write .env ------------------------------------------------------------
    DetailPrint "Writing .env..."
    FileOpen $1 "$INSTDIR\.env" w
    FileWrite $1 "GROQ_API_KEY=$GroqKey$\r$\n"
    FileWrite $1 "GEMINI_API_KEY=$GeminiKey$\r$\n"
    FileWrite $1 "BASE_OUTPUT_DIR=$INSTDIR\output$\r$\n"
    FileClose $1

    ; -- transcrire.cmd launcher -----------------------------------------------
    DetailPrint "Creating launcher..."
    FileOpen $1 "$INSTDIR\transcrire.cmd" w
    FileWrite $1 "@echo off$\r$\n"
    FileWrite $1 "cd /d $\"$INSTDIR$\"$\r$\n"
    FileWrite $1 "$\"$INSTDIR\.venv\Scripts\python.exe$\" -m cli.main %*$\r$\n"
    FileClose $1

    ; -- Start menu shortcut ---------------------------------------------------
    CreateDirectory "$SMPROGRAMS\Transcrire"
    CreateShortcut "$SMPROGRAMS\Transcrire\Transcrire.lnk" "$INSTDIR\transcrire.cmd"
    CreateShortcut "$SMPROGRAMS\Transcrire\Uninstall.lnk"  "$INSTDIR\Uninstall.exe"

    ; -- Registry entries ------------------------------------------------------
    WriteRegStr HKLM "Software\Transcrire" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\Transcrire" "Version"    "${APP_VERSION}"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}" \
        "DisplayName"     "${APP_NAME} ${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}" \
        "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}" \
        "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}" \
        "DisplayVersion"  "${APP_VERSION}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}" \
        "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}" \
        "NoRepair" 1

    ; -- Write uninstaller -----------------------------------------------------
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    DetailPrint "Installation complete."
SectionEnd

; -- Uninstaller ---------------------------------------------------------------
Section "Uninstall"
    RMDir /r "$INSTDIR\domain"
    RMDir /r "$INSTDIR\core"
    RMDir /r "$INSTDIR\services"
    RMDir /r "$INSTDIR\storage"
    RMDir /r "$INSTDIR\cli"
    RMDir /r "$INSTDIR\assets"
    RMDir /r "$INSTDIR\.venv"
    RMDir /r "$INSTDIR\bin"
    Delete "$INSTDIR\config.py"
    Delete "$INSTDIR\pyproject.toml"
    Delete "$INSTDIR\transcrire.cmd"
    Delete "$INSTDIR\.env"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    ; Remove ffmpeg from PATH
    EnVar::SetHKLM
    EnVar::DeleteValue "PATH" "$INSTDIR\bin"

    ; Remove start menu
    RMDir /r "$SMPROGRAMS\Transcrire"

    ; Remove registry
    DeleteRegKey HKLM "Software\Transcrire"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_GUID}"

    MessageBox MB_ICONINFORMATION "Transcrire has been uninstalled.$\nYour output folder was not deleted."
SectionEnd
