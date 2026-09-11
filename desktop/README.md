# Shuriken Desktop App — ⏸ PAUSED

> **Status: On hold** — Focus is on the Shuriken website first.

A Python/Tkinter desktop application that packages Shuriken tools into a native executable.

## Structure

```
desktop/
├── shuriken.py          # Entry point (tkinter)
├── app/              # GUI views, helpers, config
├── servers/          # Embedded menu tool backends (Flask servers)
├── build/            # PyInstaller build cache (gitignored)
├── dist/             # PyInstaller output (gitignored)
├── requirements.txt  # Python dependencies
├── build-exe.bat     # Build .exe via PyInstaller
├── start.bat         # Run locally without building
└── Shuriken.spec        # PyInstaller spec file
```

## Resuming Later

When ready to resume:
1. `pip install -r requirements.txt`
2. `python shuriken.py` to run locally
3. `build-exe.bat` to package as .exe

## Relationship to Website

The desktop app embeds the same backends as the website (`menu/analyzer`, `menu/mapper`, etc.) but serves them locally via Flask instead of a remote server. The website is the primary delivery mechanism.
