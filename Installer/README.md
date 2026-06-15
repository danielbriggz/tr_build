# Transcrire Installer

## Prerequisites
- [NSIS 3.x](https://nsis.sourceforge.io/Download) installed
- [EnVar plugin](https://nsis.sourceforge.io/EnVar_plug-in) placed in NSIS plugins folder

## Build steps

1. Place bundled binaries in `installer/files/`:
   - `python-3.12.0-amd64.exe` — from python.org
   - `ffmpeg.exe` + `ffprobe.exe` — from ffmpeg.org Windows build

2. Stamp file hashes:
   ```
   cd installer
   python stamp_hashes.py
   ```

3. Compile:
   ```
   makensis transcrire.nsi
   ```

4. Output: `installer/Transcrire-Setup.exe`

## What the installer does
1. Verifies CRC32 integrity of bundled binaries
2. Checks for Python 3.12 — installs silently if absent
3. Installs ffmpeg to `<InstallDir>\bin\` and adds to system PATH
4. Copies all app files to `<InstallDir>`
5. Installs Python dependencies via pip
6. Prompts for Groq + Gemini API keys → writes `.env`
7. Creates `transcrire.cmd` launcher + Start Menu shortcut
8. Registers uninstaller in Add/Remove Programs

## Uninstall
Removes all app files, binaries, shortcuts, and registry entries.
Output folder is left intact so your work isn't deleted.
