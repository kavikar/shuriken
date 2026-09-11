#!/usr/bin/env python3
"""
Shuriken — Predictive Lifecycle Assurance & Testing Engine

Entry point.  Run this file to launch the desktop app.
"""

import tkinter as tk
from app.main import ShurikenApp


def main():
    root = tk.Tk()
    ShurikenApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
