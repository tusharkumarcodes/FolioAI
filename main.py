import os
import sys
import re
import json
import time
import uuid
import threading
import html.parser
import urllib.request
import urllib.error
from pathlib import Path

import markdown
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Gio, Adw, GLib, Pango




DATA_DIR = Path.home() / ".local" / "share" / "gtk_note_app"
CONFIG_FILE = DATA_DIR / "config.json"


class PangoHTMLParser(html.parser.HTMLParser):
    """Parses HTML produced by the `markdown` library into valid GTK Pango markup."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("b", "strong"):
            self.parts.append("<b>")
        elif tag in ("i", "em"):
            self.parts.append("<i>")
        elif tag in ("code", "pre"):
            self.parts.append("<tt>")
        elif tag == "h1":
            self.parts.append('\n<span size="x-large" weight="bold">')
        elif tag == "h2":
            self.parts.append('\n<span size="large" weight="bold">')
        elif tag in ("h3", "h4", "h5", "h6"):
            self.parts.append('\n<span size="medium" weight="bold">')
        elif tag == "li":
            self.parts.append("\n  • ")
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("b", "strong"):
            self.parts.append("</b>")
        elif tag in ("i", "em"):
            self.parts.append("</i>")
        elif tag in ("code", "pre"):
            self.parts.append("</tt>")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("</span>\n")
        elif tag == "p":
            self.parts.append("\n\n")

    def handle_data(self, data):
        # Escape raw characters so Pango won't fail on &, <, >
        self.parts.append(GLib.markup_escape_text(data))


def markdown_to_pango(text: str) -> str:
    """Uses Python's `markdown` library to parse Markdown and converts it into valid Pango markup."""
    if not text:
        return ""

    try:
        html_output = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
        )
        parser = PangoHTMLParser()
        parser.feed(html_output)
        converted = "".join(parser.parts).strip()
        # Clean up excessive newlines
        converted = re.sub(r"\n{3,}", "\n\n", converted)
        return converted
    except Exception as e:
        print(f"Error in markdown_to_pango: {e}", file=sys.stderr)
        return GLib.markup_escape_text(text)


class StorageManager:
    """Manages persistent JSON storage in ~/.local/share/gtk_note_app/"""

    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, session_id: str) -> Path:
        return self.data_dir / f"{session_id}.json"

    def load_config(self):
        default_config = {
            "ollama_url": "http://localhost:11434",
            "ollama_model": "llama3",
            "dark_theme": True,
        }
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error reading config: {e}", file=sys.stderr)
        return default_config

    def save_config(self, config_dict):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}", file=sys.stderr)

    def list_sessions(self):
        """Loads all stored sessions sorted by updated_at descending with robust error handling."""
        sessions = []
        for file in self.data_dir.glob("*.json"):
            if file.name == "config.json":
                continue
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "id" in data and "title" in data:
                        sessions.append(data)
            except (json.JSONDecodeError, UnicodeDecodeError, Exception) as e:
                print(f"Skipping corrupted session file {file.name}: {e}", file=sys.stderr)
                try:
                    file.unlink(missing_ok=True)
                except Exception:
                    pass

        sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return sessions

    def save_session(self, session_data: dict):
        """Saves only clean primitive data structures to disk (never GTK widget objects)."""
        session_id = session_data["id"]
        path = self._file_path(session_id)

        clean_payload = {
            "id": session_id,
            "title": str(session_data.get("title", "Untitled")),
            "use_llm": bool(session_data.get("use_llm", False)),
            "content": str(session_data.get("content", "")),
            "messages": [
                {
                    "role": str(m.get("role", "user")),
                    "content": str(m.get("content", "")),
                }
                for m in session_data.get("messages", [])
                if isinstance(m, dict)
            ],
            "updated_at": time.time(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(clean_payload, f, indent=2, ensure_ascii=False)

    def delete_session(self, session_id: str):
        path = self._file_path(session_id)
        if path.exists():
            path.unlink(missing_ok=True)


class FolioWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_title("Folio AI")
        self.set_default_size(1100, 750)
        self.maximize()

        self.storage = StorageManager()
        self.config = self.storage.load_config()
        self.sessions = {}  # {session_id: dict_data} (pure serializable primitives)
        self.session_widgets = {}  # {session_id: {"row": Gtk.ListBoxRow, "label": Gtk.Label}}
        self.current_session_id = None
        self._is_populating = False
        self._is_generating = False
        self.active_generation = None  # Track generation across views: {"session_id": ..., "assistant_label": ...}
        self.is_connected = False  # Track Ollama connection test status

        self._build_ui()
        self._load_saved_sessions()
        self._run_startup_connection_check()

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root_box)

        # GNOME Standard HIG HeaderBar
        header_bar = Adw.HeaderBar()
        root_box.append(header_bar)

        # Main horizontal split
        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_paned.set_vexpand(True)
        main_paned.set_hexpand(True)
        main_paned.set_position(280)
        main_paned.set_wide_handle(True)
        root_box.append(main_paned)

        # -------------------------------------------------------------
        # 1. Left Sidebar
        # -------------------------------------------------------------
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar_box.set_size_request(240, -1)
        sidebar_box.add_css_class("sidebar")
        sidebar_box.set_margin_top(8)
        sidebar_box.set_margin_bottom(8)
        sidebar_box.set_margin_start(8)
        sidebar_box.set_margin_end(8)

        new_chat_btn = Gtk.Button()
        new_chat_btn.add_css_class("suggested-action")

        btn_content = Adw.ButtonContent(
            icon_name="list-add-symbolic",
            label="New Chat",
        )
        new_chat_btn.set_child(btn_content)
        new_chat_btn.connect("clicked", self._on_new_chat_clicked)
        sidebar_box.append(new_chat_btn)

        section_label = Gtk.Label(label="Recent Chats")
        section_label.set_halign(Gtk.Align.START)
        section_label.add_css_class("heading")
        section_label.set_margin_top(8)
        sidebar_box.append(section_label)

        scrolled_list = Gtk.ScrolledWindow()
        scrolled_list.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_list.set_vexpand(True)
        scrolled_list.set_hexpand(True)

        self.file_listbox = Gtk.ListBox()
        self.file_listbox.add_css_class("navigation-sidebar")
        self.file_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.file_listbox.connect("row-selected", self._on_session_selected)

        def _sort_chats_by_recency(row1, row2):
            t1 = getattr(row1, "updated_at", 0)
            t2 = getattr(row2, "updated_at", 0)
            if t1 > t2:
                return -1
            elif t1 < t2:
                return 1
            return 0

        self.file_listbox.set_sort_func(_sort_chats_by_recency)
        scrolled_list.set_child(self.file_listbox)
        sidebar_box.append(scrolled_list)

        # Pinned Settings Row
        bottom_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sidebar_box.append(bottom_separator)

        settings_button = Gtk.Button()
        settings_button.add_css_class("flat")
        settings_button.connect("clicked", self._on_settings_clicked)

        settings_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        settings_box.set_margin_top(6)
        settings_box.set_margin_bottom(6)
        settings_box.set_margin_start(6)
        settings_box.set_margin_end(6)

        gear_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        settings_label = Gtk.Label(label="Settings")
        settings_label.set_halign(Gtk.Align.START)
        settings_label.set_hexpand(True)

        settings_box.append(gear_icon)
        settings_box.append(settings_label)
        settings_button.set_child(settings_box)
        sidebar_box.append(settings_button)

        main_paned.set_start_child(sidebar_box)

        # -------------------------------------------------------------
        # 2. Main Content Workspace (Stack)
        # -------------------------------------------------------------
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)

        # Page A: Welcome State
        welcome_page = Adw.StatusPage()
        welcome_page.set_icon_name("chat-message-new-symbolic")
        welcome_page.set_title("Welcome to Folio AI")
        welcome_page.set_description(
            "Select an existing chat or click 'New Chat' to get started."
        )
        self.stack.add_named(welcome_page, "welcome")

        # Page B: Session Workspace Container
        session_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        session_container.set_margin_top(16)
        session_container.set_margin_bottom(16)
        session_container.set_margin_start(24)
        session_container.set_margin_end(24)

        # Session Header: Title + Type Badge (AI Chat or Note)
        session_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.active_filename_label = Gtk.Label(label="")
        self.active_filename_label.set_halign(Gtk.Align.START)
        self.active_filename_label.set_hexpand(True)
        self.active_filename_label.add_css_class("title-1")
        session_header_box.append(self.active_filename_label)

        self.session_badge_label = Gtk.Label(label="")
        self.session_badge_label.add_css_class("dim-label")
        self.session_badge_label.add_css_class("caption")
        session_header_box.append(self.session_badge_label)
        session_container.append(session_header_box)

        # View Stack: Plain Text Editor vs. Gemini Chat Mode
        self.session_mode_stack = Gtk.Stack()
        self.session_mode_stack.set_vexpand(True)
        self.session_mode_stack.set_hexpand(True)
        self.session_mode_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Mode 1: Standard Text Note Editor
        editor_scrolled = Gtk.ScrolledWindow()
        editor_scrolled.set_vexpand(True)
        editor_scrolled.set_hexpand(True)
        editor_scrolled.add_css_class("card")

        self.text_view = Gtk.TextView()
        self.text_view.set_monospace(True)
        self.text_view.set_top_margin(12)
        self.text_view.set_bottom_margin(12)
        self.text_view.set_left_margin(14)
        self.text_view.set_right_margin(14)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_buffer = self.text_view.get_buffer()
        self.text_buffer.connect("changed", self._on_text_changed)
        editor_scrolled.set_child(self.text_view)
        self.session_mode_stack.add_named(editor_scrolled, "editor_mode")

        # Mode 2: Gemini-Style Chat Interface
        chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        chat_box.set_vexpand(True)
        chat_box.set_hexpand(True)

        # Ensure scrollable container forbids horizontal scrolling to enforce wrapping
        self.chat_scrolled = Gtk.ScrolledWindow()
        self.chat_scrolled.set_vexpand(True)
        self.chat_scrolled.set_hexpand(True)
        self.chat_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.chat_scrolled.set_propagate_natural_width(False)

        self.chat_messages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.chat_messages_box.set_vexpand(True)
        self.chat_messages_box.set_hexpand(True)
        self.chat_messages_box.set_margin_top(8)
        self.chat_messages_box.set_margin_bottom(12)
        self.chat_messages_box.set_margin_start(12)
        self.chat_messages_box.set_margin_end(12)
        self.chat_scrolled.set_child(self.chat_messages_box)
        chat_box.append(self.chat_scrolled)

        # Sticky Bottom Chat Prompt Input Bar
        input_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_container.add_css_class("card")
        input_container.set_margin_start(4)
        input_container.set_margin_end(4)
        input_container.set_margin_bottom(4)

        self.chat_entry = Gtk.Entry()
        self.chat_entry.set_hexpand(True)
        self.chat_entry.set_placeholder_text("Ask Ollama a question...")
        self.chat_entry.add_css_class("flat")
        self.chat_entry.set_margin_start(8)
        self.chat_entry.set_margin_top(6)
        self.chat_entry.set_margin_bottom(6)
        self.chat_entry.connect("activate", self._on_send_message_clicked)
        input_container.append(self.chat_entry)

        self.send_btn = Gtk.Button()
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.add_css_class("circular")
        self.send_btn.set_icon_name("mail-send-symbolic")
        self.send_btn.set_tooltip_text("Send prompt")
        self.send_btn.set_margin_end(8)
        self.send_btn.set_margin_top(6)
        self.send_btn.set_margin_bottom(6)
        self.send_btn.connect("clicked", self._on_send_message_clicked)
        input_container.append(self.send_btn)

        chat_box.append(input_container)
        self.session_mode_stack.add_named(chat_box, "chat_mode")
        session_container.append(self.session_mode_stack)

        self.stack.add_named(session_container, "session")

        # -------------------------------------------------------------
        # Page C: Settings View (GNOME HIG Preferences Page)
        # -------------------------------------------------------------
        settings_page = Adw.PreferencesPage()
        settings_page.set_title("Settings")

        # Appearance Group
        general_group = Adw.PreferencesGroup(title="Appearance")
        dark_theme_row = Adw.ActionRow(title="Dark Style")
        dark_theme_row.set_subtitle("Follow GNOME system color-scheme preference")
        dark_switch = Gtk.Switch()
        dark_switch.set_valign(Gtk.Align.CENTER)
        dark_switch.set_active(self.config.get("dark_theme", True))
        dark_switch.connect("notify::active", self._on_theme_toggle)
        dark_theme_row.add_suffix(dark_switch)
        general_group.add(dark_theme_row)
        settings_page.add(general_group)

        # Ollama LLM Settings Group
        ollama_group = Adw.PreferencesGroup(
            title="Local AI (Ollama)",
            description="Configure your local Ollama instance for AI chat conversations.",
        )

        url_row = Adw.ActionRow(title="Endpoint URL")
        url_row.set_subtitle("Default: http://localhost:11434")
        self.url_entry = Gtk.Entry()
        self.url_entry.set_valign(Gtk.Align.CENTER)
        self.url_entry.set_text(self.config.get("ollama_url", "http://localhost:11434"))
        self.url_entry.set_size_request(260, -1)
        self.url_entry.connect("changed", self._on_config_changed)
        url_row.add_suffix(self.url_entry)
        ollama_group.add(url_row)

        model_row = Adw.ActionRow(title="Model Name")
        model_row.set_subtitle("e.g., llama3, phi3, mistral, gemma")
        self.model_entry = Gtk.Entry()
        self.model_entry.set_valign(Gtk.Align.CENTER)
        self.model_entry.set_text(self.config.get("ollama_model", "llama3"))
        self.model_entry.set_size_request(260, -1)
        self.model_entry.connect("changed", self._on_config_changed)
        model_row.add_suffix(self.model_entry)
        ollama_group.add(model_row)

        test_row = Adw.ActionRow(title="Connection Status")
        self.test_status_label = Gtk.Label(label="Not tested")
        self.test_status_label.set_valign(Gtk.Align.CENTER)
        self.test_status_label.add_css_class("dim-label")

        test_btn = Gtk.Button(label="Test Connection")
        test_btn.set_valign(Gtk.Align.CENTER)
        test_btn.connect("clicked", self._on_test_ollama_connection)
        test_row.add_suffix(self.test_status_label)
        test_row.add_suffix(test_btn)
        ollama_group.add(test_row)

        settings_page.add(ollama_group)

        storage_group = Adw.PreferencesGroup(title="Storage")
        storage_row = Adw.ActionRow(title="Data Directory")
        storage_row.set_subtitle(str(DATA_DIR))
        storage_group.add(storage_row)
        settings_page.add(storage_group)

        self.stack.add_named(settings_page, "settings")

        main_paned.set_end_child(self.stack)
        self.stack.set_visible_child_name("welcome")

    def _load_saved_sessions(self):
        saved = self.storage.list_sessions()
        if not saved:
            sample_session = {
                "id": str(uuid.uuid4()),
                "title": "Welcome Note",
                "use_llm": False,
                "content": "# Welcome to Folio AI\n\nThis is a standard text note.\nWhen creating a new chat via 'New Chat', you can enable 'Use Local LLM' in the dialog to start an AI chat.",
                "messages": [],
            }
            self.storage.save_session(sample_session)
            self._add_session_row(sample_session, prepend=False)
        else:
            for s in saved:
                if "use_llm" not in s:
                    s["use_llm"] = False
                self._add_session_row(s, prepend=False)

    def _add_session_row(self, session_data: dict, prepend: bool = False):
        session_id = session_data["id"]
        title = session_data.get("title", "Untitled")
        is_llm = session_data.get("use_llm", False)

        row = Gtk.ListBoxRow()
        row.session_id = session_id
        row.updated_at = float(session_data.get("updated_at", time.time()))

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)
        row_box.set_margin_start(10)
        row_box.set_margin_end(6)

        icon_name = "chat-message-new-symbolic" if is_llm else "text-x-generic-symbolic"
        icon = Gtk.Image.new_from_icon_name(icon_name)

        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_ellipsize(3)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("view-more-symbolic")
        menu_button.add_css_class("flat")
        menu_button.add_css_class("circular")
        menu_button.set_tooltip_text("Session options")

        popover = Gtk.Popover()
        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pop_box.set_margin_top(6)
        pop_box.set_margin_bottom(6)
        pop_box.set_margin_start(6)
        pop_box.set_margin_end(6)

        rename_btn = Gtk.Button()
        rename_btn.add_css_class("flat")
        rename_content = Adw.ButtonContent(
            icon_name="document-edit-symbolic",
            label="Rename",
        )
        rename_btn.set_child(rename_content)
        rename_btn.connect("clicked", self._on_rename_session_clicked, session_id, popover)
        pop_box.append(rename_btn)

        delete_btn = Gtk.Button()
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("destructive-action")
        del_content = Adw.ButtonContent(
            icon_name="user-trash-symbolic",
            label="Delete",
        )
        delete_btn.set_child(del_content)
        delete_btn.connect("clicked", self._on_delete_session_clicked, session_id, popover)
        pop_box.append(delete_btn)

        popover.set_child(pop_box)
        menu_button.set_popover(popover)

        row_box.append(icon)
        row_box.append(label)
        row_box.append(menu_button)
        row.set_child(row_box)

        self.session_widgets[session_id] = {
            "row": row,
            "label": label,
        }

        clean_data = {
            "id": session_id,
            "title": title,
            "use_llm": is_llm,
            "content": session_data.get("content", ""),
            "messages": session_data.get("messages", []),
            "updated_at": float(session_data.get("updated_at", time.time())),
        }
        self.sessions[session_id] = clean_data

        self.file_listbox.append(row)
        self.file_listbox.invalidate_sort()

        return row

    def _on_session_selected(self, listbox, row):
        if row is None or not hasattr(row, "session_id"):
            return

        session_id = row.session_id
        if session_id not in self.sessions:
            return

        self.current_session_id = session_id
        session_info = self.sessions[session_id]
        self.active_filename_label.set_text(session_info.get("title", "Untitled"))

        self._is_populating = True
        self.text_buffer.set_text(session_info.get("content", ""))
        self._is_populating = False

        self._update_session_view()
        self.stack.set_visible_child_name("session")

    def _run_startup_connection_check(self):
        """Runs the settings connection test in the background upon application startup."""
        self._test_ollama_connection_async()

    def _test_ollama_connection_async(self, on_complete=None):
        endpoint = f"{self.url_entry.get_text().strip().rstrip('/')}/api/tags"

        def test_worker():
            try:
                req = urllib.request.Request(endpoint, method="GET")
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    model_names = ", ".join(models[:3]) if models else "None"
                    msg = f"Connected! Available: {model_names}"

                    def on_success():
                        self.is_connected = True
                        self.test_status_label.set_text(msg)
                        if on_complete:
                            on_complete(True)

                    GLib.idle_add(on_success)
            except Exception as e:
                def on_fail():
                    self.is_connected = False
                    self.test_status_label.set_text(f"Failed: {str(e)}")
                    if on_complete:
                        on_complete(False)

                GLib.idle_add(on_fail)

        threading.Thread(target=test_worker, daemon=True).start()

    def _update_session_view(self):
        if not self.current_session_id or self.current_session_id not in self.sessions:
            return

        session = self.sessions[self.current_session_id]
        use_llm = session.get("use_llm", False)

        if use_llm:
            self.session_mode_stack.set_visible_child_name("chat_mode")
            model_name = self.config.get("ollama_model", "llama3")
            self.session_badge_label.set_text(f"AI Chat • {model_name}")
            self._rebuild_chat_messages(session.get("messages", []))

            # Restore in-flight generating message bubble if user switched back to this session
            if (
                self._is_generating
                and self.active_generation
                and self.active_generation.get("session_id") == self.current_session_id
            ):
                current_text = self.active_generation.get("accumulated_text", "")
                display_text = current_text if current_text else "Generating response..."
                new_assistant_label = self._render_message_bubble("assistant", display_text)
                self.active_generation["assistant_label"] = new_assistant_label
                self.send_btn.set_sensitive(False)
                self._scroll_chat_to_bottom()
            else:
                self.send_btn.set_sensitive(not self._is_generating)
        else:
            self.session_mode_stack.set_visible_child_name("editor_mode")
            self.session_badge_label.set_text("Text Note")

    # -------------------------------------------------------------
    # Chat Messages Rendering (Properly Bounded & Wrapped)
    # -------------------------------------------------------------
    def _rebuild_chat_messages(self, messages):
        while child := self.chat_messages_box.get_first_child():
            self.chat_messages_box.remove(child)

        for msg in messages:
            self._render_message_bubble(msg["role"], msg["content"])

        self._scroll_chat_to_bottom()

    def _render_message_bubble(self, role: str, content: str):
        is_user = role == "user"

        bubble_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bubble_row.set_hexpand(True)

        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bubble.set_hexpand(True)
        bubble.set_margin_top(4)
        bubble.set_margin_bottom(4)

        if is_user:
            bubble_row.set_halign(Gtk.Align.END)
            bubble.add_css_class("card")
            bubble.set_margin_start(80)
            bubble.set_margin_end(6)
            author_text = "You"
        else:
            bubble_row.set_halign(Gtk.Align.START)
            bubble.set_margin_start(6)
            bubble.set_margin_end(80)
            author_text = f"Ollama ({self.config.get('ollama_model', 'local')})"

        author_label = Gtk.Label(label=author_text)
        author_label.set_halign(Gtk.Align.START)
        author_label.add_css_class("caption")
        author_label.add_css_class("dim-label")
        author_label.set_margin_top(6)
        author_label.set_margin_start(10)
        author_label.set_margin_end(10)

        # Word-wrapped content label strictly bounded horizontally
        msg_label = Gtk.Label()
        msg_label.set_halign(Gtk.Align.START)
        msg_label.set_hexpand(True)
        msg_label.set_wrap(True)
        msg_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        msg_label.set_natural_wrap_mode(Gtk.NaturalWrapMode.NONE)
        msg_label.set_selectable(True)
        msg_label.set_margin_start(12)
        msg_label.set_margin_end(12)
        msg_label.set_margin_bottom(10)

        self._apply_markup(msg_label, content)

        bubble.append(author_label)
        bubble.append(msg_label)
        bubble_row.append(bubble)
        self.chat_messages_box.append(bubble_row)
        return msg_label

    def _apply_markup(self, label: Gtk.Label, raw_text: str):
        """Converts raw Markdown text to Pango markup and applies it safely."""
        pango_markup = markdown_to_pango(raw_text)
        try:
            label.set_markup(pango_markup)
        except Exception:
            label.set_text(raw_text)

    def _mark_session_updated(self, session_id: str):
        """Updates the session timestamp and re-sorts the sidebar so the active chat rises to the top."""
        now = time.time()
        if session_id in self.sessions:
            self.sessions[session_id]["updated_at"] = now
        if session_id in self.session_widgets:
            self.session_widgets[session_id]["row"].updated_at = now
        self.file_listbox.invalidate_sort()

    def _scroll_chat_to_bottom(self, attempts: int = 3):
        """Reliably scrolls to the bottom of the chat view across allocation frames."""
        def do_scroll(remaining):
            adj = self.chat_scrolled.get_vadjustment()
            target = max(0.0, adj.get_upper() - adj.get_page_size())
            adj.set_value(target)
            if remaining > 0:
                GLib.idle_add(do_scroll, remaining - 1)
            return False

        GLib.idle_add(do_scroll, attempts)

    # -------------------------------------------------------------
    # Ollama API Execution (Background Thread with real-time multi-turn streaming)
    # -------------------------------------------------------------
    def _on_send_message_clicked(self, *args):
        if self._is_generating or not self.current_session_id:
            return

        prompt = self.chat_entry.get_text().strip()
        if not prompt:
            return

        self.chat_entry.set_text("")
        session = self.sessions[self.current_session_id]

        # 1. Render User Message Bubble and save to session history
        session["messages"].append({"role": "user", "content": prompt})
        self._render_message_bubble("user", prompt)
        self.storage.save_session(session)
        self._mark_session_updated(self.current_session_id)
        self._scroll_chat_to_bottom(attempts=4)

        # 2. Render Assistant Bubble with Initial Status
        assistant_label = self._render_message_bubble("assistant", "Generating response...")
        self._scroll_chat_to_bottom(attempts=4)

        # 3. Snapshot the conversation messages for multi-turn context (with safeguard limit of last 30 turns)
        history_snapshot = [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in session.get("messages", [])
        ][-30:]

        # 4. Track active generation state so switching tabs/settings preserves it
        self._is_generating = True
        self.active_generation = {
            "session_id": self.current_session_id,
            "assistant_label": assistant_label,
            "accumulated_text": "",
        }
        self.send_btn.set_sensitive(False)

        threading.Thread(
            target=self._query_ollama_worker,
            args=(self.current_session_id, history_snapshot),
            daemon=True,
        ).start()

    def _query_ollama_worker(self, target_session_id, history_messages):
        """Worker thread streaming multi-turn conversation in real-time from Ollama /api/chat with think=False"""
        endpoint = f"{self.config.get('ollama_url', 'http://localhost:11434').rstrip('/')}/api/chat"
        model = self.config.get("ollama_model", "llama3")

        # Prepend system instruction to enforce direct answers and disable thinking mode
        messages_payload = [
            {
                "role": "system",
                "content": "Provide only the direct response or answer. Do not include any internal thinking, thoughts, or thinking process.",
            }
        ] + history_messages

        payload = {
            "model": model,
            "messages": messages_payload,
            "stream": True,
            "think": False,
        }

        accumulated_chunks = []
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req) as resp:
                for line in resp:
                    if not line:
                        continue
                    try:
                        chunk_data = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue

                    chunk_text = chunk_data.get("message", {}).get("content", "")
                    if chunk_text:
                        accumulated_chunks.append(chunk_text)
                        full_so_far = "".join(accumulated_chunks)
                        # Clean any think tags if present
                        cleaned_so_far = re.sub(r"<think>.*?</think>", "", full_so_far, flags=re.DOTALL)
                        GLib.idle_add(self._on_ollama_chunk, target_session_id, cleaned_so_far)

            final_text = "".join(accumulated_chunks).strip()
            final_text = re.sub(r"<think>.*?</think>", "", final_text, flags=re.DOTALL).strip()
            if not final_text:
                final_text = "(Received empty response from Ollama)"

        except urllib.error.URLError as e:
            final_text = (
                f"Connection error: Could not reach Ollama at {endpoint}.\n"
                f"Make sure Ollama is running (`ollama serve`). ({e.reason})"
            )
        except Exception as e:
            final_text = f"Error communicating with Ollama: {str(e)}"

        GLib.idle_add(self._on_ollama_finished, target_session_id, final_text)

    def _on_ollama_chunk(self, target_session_id, accumulated_text):
        if self.active_generation and self.active_generation.get("session_id") == target_session_id:
            self.active_generation["accumulated_text"] = accumulated_text
            if self.current_session_id == target_session_id:
                label = self.active_generation.get("assistant_label")
                if label:
                    self._apply_markup(label, accumulated_text)
                    self._scroll_chat_to_bottom(attempts=2)
        return False

    def _on_ollama_finished(self, target_session_id, final_text):
        if target_session_id in self.sessions:
            session = self.sessions[target_session_id]
            session["messages"].append({"role": "assistant", "content": final_text})
            self.storage.save_session(session)
            self._mark_session_updated(target_session_id)

            # If the user is currently viewing this session, update the label or rebuild
            if self.current_session_id == target_session_id:
                if self.active_generation and self.active_generation.get("assistant_label"):
                    try:
                        self._apply_markup(self.active_generation["assistant_label"], final_text)
                    except Exception:
                        self._rebuild_chat_messages(session.get("messages", []))
                else:
                    self._rebuild_chat_messages(session.get("messages", []))
                self._scroll_chat_to_bottom(attempts=4)

        self._is_generating = False
        self.active_generation = None
        self.send_btn.set_sensitive(True)
        return False

    def _on_test_ollama_connection(self, button):
        self.test_status_label.set_text("Testing...")
        self._test_ollama_connection_async()

    def _on_config_changed(self, entry):
        self.config["ollama_url"] = self.url_entry.get_text().strip()
        self.config["ollama_model"] = self.model_entry.get_text().strip()
        self.storage.save_config(self.config)

    def _on_text_changed(self, buffer):
        if self._is_populating or not self.current_session_id:
            return

        session = self.sessions[self.current_session_id]
        start_iter = buffer.get_start_iter()
        end_iter = buffer.get_end_iter()
        session["content"] = buffer.get_text(start_iter, end_iter, True)
        self.storage.save_session(session)
        self._mark_session_updated(self.current_session_id)

    # -------------------------------------------------------------
    # New Chat Creation Dialog with 'Use Local LLM' Switch
    # -------------------------------------------------------------
    def _on_new_chat_clicked(self, button):
        dialog = Adw.AlertDialog(
            heading="New Chat",
            body="Configure and name your new chat:",
        )

        dialog_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        dialog_content.set_margin_top(6)
        dialog_content.set_margin_bottom(6)

        entry = Gtk.Entry()
        placeholder = f"Chat {len(self.sessions) + 1}"
        entry.set_placeholder_text(placeholder)
        entry.set_activates_default(True)
        dialog_content.append(entry)

        # Toggle Switch Row in Creation Dialog
        llm_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        llm_row.set_margin_top(6)

        llm_label = Gtk.Label(label="Use Local LLM (AI Chat)")
        llm_label.set_halign(Gtk.Align.START)
        llm_label.set_hexpand(True)
        llm_row.append(llm_label)

        llm_switch = Gtk.Switch()
        llm_switch.set_valign(Gtk.Align.CENTER)
        # Enable or disable the toggle switch based on test connection status
        llm_switch.set_sensitive(self.is_connected)
        if not self.is_connected:
            llm_switch.set_active(False)
            llm_switch.set_tooltip_text("Ollama is not connected. Test connection in Settings to enable.")
        else:
            llm_switch.set_active(False)
            llm_switch.set_tooltip_text("Toggle to enable Local LLM AI Chat")
        llm_row.append(llm_switch)

        dialog_content.append(llm_row)
        dialog.set_extra_child(dialog_content)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")
        dialog.set_close_response("cancel")

        submitted = False

        def submit_creation():
            nonlocal submitted
            if submitted:
                return
            submitted = True

            raw_title = entry.get_text().strip()
            title = raw_title if raw_title else placeholder
            if "." in title:
                title = title.rsplit(".", 1)[0]

            use_llm_choice = llm_switch.get_active() if self.is_connected else False

            new_session = {
                "id": str(uuid.uuid4()),
                "title": title,
                "use_llm": use_llm_choice,
                "content": "",
                "messages": [],
            }

            self.storage.save_session(new_session)
            new_row = self._add_session_row(new_session, prepend=True)
            self.file_listbox.select_row(new_row)
            dialog.force_close()

        def on_dialog_response(diag, response):
            if response == "create":
                submit_creation()

        # Keyboard controller to handle Enter / Return key anywhere inside the dialog
        key_controller = Gtk.EventControllerKey()

        def on_key_pressed(ctrl, keyval, keycode, state):
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                submit_creation()
                return True
            return False

        key_controller.connect("key-pressed", on_key_pressed)
        dialog.add_controller(key_controller)

        # Pressing Enter in text entry triggers submit_creation
        entry.connect("activate", lambda e: submit_creation())
        dialog.connect("response", on_dialog_response)
        dialog.present(self)

    def _on_rename_session_clicked(self, button, session_id, popover):
        popover.popdown()

        if session_id not in self.sessions:
            return

        current_title = self.sessions[session_id]["title"]

        dialog = Adw.AlertDialog(
            heading="Rename Chat",
            body="Enter a new title for this chat:",
        )

        entry = Gtk.Entry()
        entry.set_text(current_title)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        submitted = False

        def submit_rename():
            nonlocal submitted
            if submitted:
                return
            submitted = True

            new_title = entry.get_text().strip()
            if not new_title:
                new_title = current_title

            if "." in new_title:
                new_title = new_title.rsplit(".", 1)[0]

            session = self.sessions[session_id]
            session["title"] = new_title

            if session_id in self.session_widgets:
                self.session_widgets[session_id]["label"].set_text(new_title)

            self.storage.save_session(session)

            if self.current_session_id == session_id:
                self.active_filename_label.set_text(new_title)

            dialog.force_close()

        def on_dialog_response(diag, response):
            if response == "save":
                submit_rename()

        key_controller = Gtk.EventControllerKey()

        def on_key_pressed(ctrl, keyval, keycode, state):
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                submit_rename()
                return True
            return False

        key_controller.connect("key-pressed", on_key_pressed)
        dialog.add_controller(key_controller)

        entry.connect("activate", lambda e: submit_rename())
        dialog.connect("response", on_dialog_response)
        dialog.present(self)

    def _on_delete_session_clicked(self, button, session_id, popover):
        popover.popdown()

        if session_id not in self.sessions:
            return

        session_widget_info = self.session_widgets.pop(session_id, None)
        del self.sessions[session_id]

        self.storage.delete_session(session_id)

        if self.current_session_id == session_id:
            self.current_session_id = None
            self.text_buffer.set_text("")
            self.active_filename_label.set_text("")
            self.session_badge_label.set_text("")
            self.stack.set_visible_child_name("welcome")

        if session_widget_info and "row" in session_widget_info:
            self.file_listbox.remove(session_widget_info["row"])

    def _on_settings_clicked(self, button):
        self.file_listbox.unselect_all()
        self.current_session_id = None
        self.stack.set_visible_child_name("settings")

    def _on_theme_toggle(self, switch, gparam):
        manager = Adw.StyleManager.get_default()
        is_dark = switch.get_active()
        self.config["dark_theme"] = is_dark
        self.storage.save_config(self.config)
        if is_dark:
            manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        else:
            manager.set_color_scheme(Adw.ColorScheme.PREFER_LIGHT)


class FolioApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="org.example.FolioAI",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = FolioWindow(application=self)
        win.present()


def main():
    app = FolioApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
