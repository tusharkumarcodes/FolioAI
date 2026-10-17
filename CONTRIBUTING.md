# Contributing to Folio AI

Thank you for your interest in contributing to **Folio AI**! We welcome community contributions, bug reports, and suggestions.

---

## 🛠️ Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/<your-username>/folio-ai.git
   cd folio-ai
   ```

2. **Install system dependencies**:
   - **Fedora**:
     ```bash
     sudo dnf install python3-gobject gtk4 libadwaita python3-markdown
     ```
   - **Ubuntu / Debian**:
     ```bash
     sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-markdown
     ```
   - **Arch Linux**:
     ```bash
     sudo pacman -S python-gobject gtk4 libadwaita python-markdown
     ```

3. **Run Ollama**:
   Ensure Ollama is running and has at least one model pulled:
   ```bash
   ollama serve
   ollama pull llama3
   ```

4. **Launch the application**:
   ```bash
   python3 main.py
   ```

---

## 📌 Coding Guidelines

- **GTK 4 / Libadwaita**: Follow [GNOME Human Interface Guidelines (HIG)](https://developer.gnome.org/hig/). Use native Adwaita widgets (`Adw.HeaderBar`, `Adw.PreferencesPage`, `Adw.AlertDialog`, etc.) rather than deprecated GTK constructs.
- **Pango & Markdown**: Any markdown extension or parser addition must output safe, valid Pango markup using `GLib.markup_escape_text`.
- **Thread Safety**: Never interact directly with GTK widgets from background threads; always dispatch updates to the main GUI loop using `GLib.idle_add()`.
- **Pure Primitives for Persistence**: When modifying the session schema, ensure only JSON-serializable primitives (`str`, `int`, `float`, `bool`, `list`, `dict`) are passed to `StorageManager`. Never store GTK widget objects inside session dictionaries.

---

## 🐛 Reporting Issues & Feature Requests

- You can open an issue on GitHub. Please search existing issues before filing a new one.
- In case you find a bug or issue, you can also reach out directly via email at [tusharkumar.mohali@gmail.com](mailto:tusharkumar.mohali@gmail.com).
- When reporting a bug, please include your Linux distribution, GNOME/GTK version, Ollama version, and model name.
