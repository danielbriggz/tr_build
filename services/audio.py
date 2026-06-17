import shutil
import subprocess
from pathlib import Path


def check_ffmpeg() -> None:
    """Verify ffmpeg is available on PATH. Called once at pipeline start."""
    if not shutil.which("ffmpeg"):
        raise EnvironmentError(
            "ffmpeg not found. Please reinstall Transcrire to restore bundled ffmpeg."
        )


def compress_for_groq(input_path: Path, output_path: Path) -> Path:
    """
    Compress audio to mono MP3 at 64kbps — keeps files under Groq's 25MB limit.
    Returns the output path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ac", "1",           # mono
        "-ar", "16000",       # 16kHz sample rate
        "-b:a", "64k",        # 64kbps bitrate
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg compression failed:\n{result.stderr}")
    return output_path


def pick_file_dialog() -> str | None:
    """
    Open a Windows file picker dialog and return the selected file path.
    Returns None if the user cancels.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()        # hide the empty root window
        root.wm_attributes("-topmost", True)  # dialog appears on top

        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg"),
                ("All files",   "*.*"),
            ],
        )
        root.destroy()
        return path or None

    except Exception as e:
        raise RuntimeError(f"File picker failed: {e}")


def pick_file_dialog() -> str | None:
    """
    Open a Windows file picker dialog and return the selected file path.
    Returns None if the user cancels.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()       # hide the empty root window
        root.wm_attributes("-topmost", True)  # bring picker to front

        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg"),
                ("All files",   "*.*"),
            ],
        )
        root.destroy()
        return path or None

    except Exception as e:
        raise EnvironmentError(f"Could not open file picker: {e}")


def pick_file_dialog() -> str | None:
    """
    Open a Windows file picker dialog and return the selected file path.
    Returns None if the user cancels.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg"),
                ("All files",   "*.*"),
            ],
        )
        root.destroy()
        return path or None

    except Exception as e:
        raise RuntimeError(f"File picker failed: {e}")