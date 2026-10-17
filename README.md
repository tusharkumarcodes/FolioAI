# Folio AI (GTK 4 & Libadwaita Local AI Chat & Notes)

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](file:///home/tushar/Development/project003/LICENSE)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux%20%2F%20GNOME-green.svg)](#prerequisites)
[![GTK: 4.0](https://img.shields.io/badge/GTK-4.0-red.svg)](https://gtk.org)
[![Libadwaita: 1](https://img.shields.io/badge/Libadwaita-1.0-purple.svg)](https://gnome.pages.gitlab.gnome.org/libadwaita/)
[![Ollama: Local AI](https://img.shields.io/badge/Ollama-Local%20AI-orange.svg)](https://ollama.com)

**Folio AI** is a native, modern, and persistent AI chat and notes application designed for GNOME (Fedora, Arch, Debian/Ubuntu, and modern Linux desktops). It is built with **Python 3**, **GTK 4**, **Libadwaita**, and local **Ollama** LLM integration.

---

## ✨ Features

- **GNOME Human Interface Guidelines (HIG) Design**:
  - Fully native Libadwaita aesthetic with responsive sidebar, dynamic header bar, and rounded card styling.
  - Light and Dark style toggle supporting GNOME's system color scheme preference.
- **Dual-Mode Workspace**:
  - **Text Notes**: Monospace editor with auto-save and word wrapping.
  - **Local AI Chat**: Multi-turn chat interface with chat bubbles styled after modern AI assistants.
- **Real-Time Streaming Generation**:
  - Non-blocking background worker streaming responses directly from Ollama's `/api/chat` endpoint.
  - Built-in thinking mode suppression (`think: False` and `<think>` tag stripping) for clean, immediate answers.
  - State preservation across session switches while generation is in progress.
- **Markdown & Pango Rendering**:
  - Rich text formatting using Python's `markdown` library with `fenced_code`, `tables`, `nl2br`, and `sane_lists`.
  - Custom HTML-to-Pango parser converting markdown tags (`<b>`, `<i>`, `<tt>`, headings, lists) to safe GTK Pango markup with strict entity escaping.
- **Strict Layout Constraints & Text Wrapping**:
  - Unbreakable horizontal constraints preventing horizontal scroll expansion on long text or code blocks.
  - Automatic vertical scroll-to-bottom across layout allocation frames.
- **Session & Storage Management**:
  - Chats and notes stored locally as clean JSON in `~/.local/share/gtk_note_app/`.
  - Recency-based sorting so the most recently active session moves to the top of the sidebar.
  - Context menu options for renaming and deleting sessions.
- **Integrated Settings & Health Check**:
  - Connection status check and model discovery (`/api/tags`) on startup and on demand.
  - Configurable Ollama API endpoint (default: `http://localhost:11434`) and model name (e.g., `llama3`, `mistral`, `phi3`, `gemma`).
  - Automatic validation ensuring Ollama is accessible before enabling AI mode on new chats.

---

## 📋 Prerequisites

### 1. System Dependencies by Distribution

#### Fedora / RHEL
```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita python3-markdown
```

#### Ubuntu / Debian / Linux Mint
```bash
sudo apt update
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-markdown
```

#### Arch Linux / Manjaro
```bash
sudo pacman -S python python-gobject gtk4 libadwaita python-markdown
```

### 2. Ollama (Local LLM Provider)

Install [Ollama](https://ollama.com/) if you haven't already:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Start the Ollama daemon and pull your preferred model:

```bash
# Start Ollama service
ollama serve

# In another terminal, pull a model (default is llama3)
ollama pull llama3
```

> [!TIP]
> You can also use other models such as `mistral`, `phi3`, `gemma2`, or `qwen2.5`. Remember to update the model name in **Settings** within Folio AI.

---

## 🚀 Running the Application

Clone the repository and launch the app:

```bash
python3 main.py
```

### Optional: Desktop Launcher Integration

To add Folio AI to your GNOME application launcher:

```bash
# Copy desktop file to your user applications folder
mkdir -p ~/.local/share/applications
cp org.example.FolioAI.desktop ~/.local/share/applications/

# Adjust path in the installed desktop entry to your clone directory:
sed -i "s|/home/tushar/Development/project003|$(pwd)|g" ~/.local/share/applications/org.example.FolioAI.desktop

# Update desktop database
update-desktop-database ~/.local/share/applications/
```

---

## ⚙️ Configuration & Data Storage

- **Data Directory**: `~/.local/share/gtk_note_app/`
  - `config.json`: Saves preferences including `ollama_url`, `ollama_model`, and `dark_theme`.
  - `<session-id>.json`: Individual session data containing chat history or note content, title, and last updated timestamp.

---

## 🛠️ Usage Guide

1. **Create a Note or Chat**:
   - Click the **New Chat** button in the sidebar.
   - Enter a name for your session.
   - Toggle **Use Local LLM (AI Chat)** to enable Ollama mode, or leave it off for a standard text note.
   - Press <kbd>Enter</kbd> or click **Create**.
2. **Chatting with Local AI**:
   - Type your prompt in the bottom entry and press <kbd>Enter</kbd> (or click the Send button).
   - Responses stream in real-time with Markdown and code formatting.
3. **Managing Sessions**:
   - Click the three-dots menu icon next to any session in the sidebar to **Rename** or **Delete**.
4. **Settings & Health Check**:
   - Click **Settings** at the bottom of the sidebar to adjust the Ollama URL, switch models, test connectivity, or toggle dark style.

---

## 🤝 Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](file:///home/tushar/Development/project003/CONTRIBUTING.md) for setup instructions and development guidelines.

---

## 📄 License

This project is licensed under the terms of the [GNU General Public License v3.0 (GPL-3.0)](file:///home/tushar/Development/project003/LICENSE).
