; ─────────────────────────────────────────────────────────────────────────────
; Transcrire Installer — NSIS Script
; Targets: Windows 10/11 x64
; Bundles: Python 3.12, ffmpeg, app source
; ─────────────────────────────────────────────────────────────────────────────

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; ── Metadata ──────────────────────────────────────────────────────────────────
Name              "Transcrire"
OutFile           "Transcrire-Setup.exe"
InstallDir        "$PROGRAMFILES64\Transcrire"
InstallDirRegKey  HKLM "Software\Transcrire" "InstallDir"
RequestExecutionLevel admin
SetCompressor     /SOLID lzma

; ── Version ───────────────────────────────────────────────────────────────────
!define APP_NAME    "Transcrire"
!define APP_VERSION "0.1.0"
!define APP_GUID    "{D4A2F3B1-9C7E-4E8A-A2D1-0F3C5B7E9D2A}"
!define PYTHON_VER  "3.12"
!define PYTHON_MIN  "3.12.0"

; ── MUI Pages ─────────────────────────────────────────────────────────────────
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

; ── API Key page variables ────────────────────────────────────────────────────
Var GroqKey
Var GeminiKey
Var APIKeysDialog
Var GroqField
Var GeminiField

; ── API Keys custom page ──────────────────────────────────────────────────────
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

; ── Integrity check helper ────────────────────────────────────────────────────
!macro CheckFileHash FILE EXPECTED_CRC
    CRC32 $0 "${FILE}"
    ${If} $0 != "${EXPECTED_CRC}"
        MessageBox MB_ICONSTOP "Integrity check failed for ${FILE}.$\nThe installer may be corrupted. Please re-download."
        Abort
    ${EndIf}
!macroend

; ── Main install section ──────────────────────────────────────────────────────
Section "Transcrire" SEC_MAIN
    SectionIn RO  ; required, cannot be deselected

    SetOutPath "$INSTDIR"

    ; ── Integrity checks ───────────────────────────────────────────────────────
    DetailPrint "Verifying installer integrity..."
    !insertmacro CheckFileHash "$EXEDIR\files\python-3.12.0-amd64.exe" "PYTHON_CRC_PLACEHOLDER"
    !insertmacro CheckFileHash "$EXEDIR\files\ffmpeg.exe"              "FFMPEG_CRC_PLACEHOLDER"

    ; ── Python detection + silent install ─────────────────────────────────────
    DetailPrint "Checking for Python ${PYTHON_VER}..."
    ReadRegStr $0 HKLM "SOFTWARE\Python\PythonCore\${PYTHON_VER}\InstallPath" ""
    ${If} $0 == ""
        DetailPrint "Python ${PYTHON_VER} not found — installing silently..."
        File "files\python-3.12.0-amd64.exe"
        ExecWait '"$INSTDIR\python-3.12.0-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1' $0
        ${If} $0 != 0
            MessageBox MB_ICONSTOP "Python installation failed (exit code $0). Please install Python ${PYTHON_VER} manually and retry."
            Abort
        ${EndIf}
        DetailPrint "Python installed."
        Delete "$INSTDIR\python-3.12.0-amd64.exe"
    ${Else}
        DetailPrint "Python ${PYTHON_VER} found at $0 — skipping."
    ${EndIf}

    ; ── ffmpeg ────────────────────────────────────────────────────────────────
    DetailPrint "Installing ffmpeg..."
    CreateDirectory "$INSTDIR\bin"
    File "/oname=$INSTDIR\bin\ffmpeg.exe" "files\ffmpeg.exe"
    File "/oname=$INSTDIR\bin\ffprobe.exe" "files\ffprobe.exe"

    ; Add ffmpeg to system PATH
    EnVar::SetHKLM
    EnVar::AddValue "PATH" "$INSTDIR\bin"

    ; ── App files ─────────────────────────────────────────────────────────────
    DetailPrint "Installing Transcrire..."
    File /r "..\domain"
    File /r "..\core"
    File /r "..\services"
    File /r "..\storage"
    File /r "..\cli"
    File /r "..\assets"
    File    "..\config.py"
    File    "..\pyproject.toml"

    ; ── Install Python dependencies via pip ───────────────────────────────────
    DetailPrint "Installing Python dependencies..."
    ExecWait 'python -m pip install --quiet -r "$INSTDIR\requirements.txt"' $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "Dependency installation failed. Check your internet connection and retry."
        Abort
    ${EndIf}

    ; ── Write .env ────────────────────────────────────────────────────────────
    DetailPrint "Writing .env..."
    FileOpen $1 "$INSTDIR\.env" w
    FileWrite $1 "GROQ_API_KEY=$GroqKey$\r$\n"
    FileWrite $1 "GEMINI_API_KEY=$GeminiKey$\r$\n"
    FileWrite $1 "BASE_OUTPUT_DIR=$INSTDIR\output$\r$\n"
    FileWrite $1 "FONTS_DIR=$INSTDIR\assets\fonts$\r$\n"
    FileClose $1

    ; ── transcrire.cmd launcher ───────────────────────────────────────────────
    DetailPrint "Creating launcher..."
    FileOpen $1 "$INSTDIR\transcrire.cmd" w
    FileWrite $1 "@echo off$\r$\n"
    FileWrite $1 "cd /d $\"$INSTDIR$\"$\r$\n"
    FileWrite $1 "python -m cli.main %*$\r$\n"
    FileClose $1

    ; ── Start menu shortcut ───────────────────────────────────────────────────
    CreateDirectory "$SMPROGRAMS\Transcrire"
    CreateShortcut "$SMPROGRAMS\Transcrire\Transcrire.lnk" "$INSTDIR\transcrire.cmd"
    CreateShortcut "$SMPROGRAMS\Transcrire\Uninstall.lnk"  "$INSTDIR\Uninstall.exe"

    ; ── Registry entries ──────────────────────────────────────────────────────
    WriteRegStr HKLM "Software\Transcrire" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\Transcrire" "Version"    "${APP_VERSION}"

    ; Add/Remove Programs entry
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

    ; ── Write uninstaller ─────────────────────────────────────────────────────
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    DetailPrint "Installation complete."
SectionEnd

; ── Uninstaller ───────────────────────────────────────────────────────────────
Section "Uninstall"
    ; Remove app files
    RMDir /r "$INSTDIR\domain"
    RMDir /r "$INSTDIR\core"
    RMDir /r "$INSTDIR\services"
    RMDir /r "$INSTDIR\storage"
    RMDir /r "$INSTDIR\cli"
    RMDir /r "$INSTDIR\assets"
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

    MessageBox MB_ICONINFORMATION "Transcrire has been uninstalled.$\n$\nYour output folder was not deleted."
SectionEnd
