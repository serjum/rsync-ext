from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from rsync_ext.config import ConnectionStore, new_connection_id
from rsync_ext.constants import APP_ID, APP_NAME
from rsync_ext.deps import check_dependencies
from rsync_ext.logging_utils import setup_logging
from rsync_ext.models import Connection
from rsync_ext.secrets import SecretStore
from rsync_ext.transfer import CommandResult, build_transfer_plan, map_command_error, test_connection
from rsync_ext.transfer import should_retry_with_inplace

LOGGER = setup_logging()


def launch_app(
    *,
    mode: str,
    connection_id: str | None = None,
    dest_path: str | None = None,
    sources: list[str] | None = None,
) -> int:
    Adw.init()
    LOGGER.info(
        "Launching app mode=%s connection_id=%s sources=%d",
        mode,
        connection_id,
        len(sources or []),
    )
    app = RsyncExtApplication(
        mode=mode,
        connection_id=connection_id,
        dest_path=dest_path,
        sources=sources or [],
    )
    return app.run([])


class RsyncExtApplication(Adw.Application):
    def __init__(
        self,
        *,
        mode: str,
        connection_id: str | None = None,
        dest_path: str | None = None,
        sources: list[str] | None = None,
    ) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.mode = mode
        self.connection_id = connection_id
        self.dest_path = dest_path
        self.sources = sources or []
        self.store = ConnectionStore()
        self.secret_store = SecretStore()
        self._child_windows: set[Adw.Window] = set()

    def do_activate(self) -> None:
        LOGGER.info("Application activate mode=%s", self.mode)
        if self.mode == "send":
            if not self.connection_id:
                window = ConnectionsWindow(self, status_message="No connection selected.")
            else:
                try:
                    connection = self.store.get(self.connection_id)
                except KeyError:
                    window = ConnectionsWindow(
                        self,
                        status_message=f"Unknown connection '{self.connection_id}'.",
                    )
                else:
                    window = SendWindow(
                        self,
                        connection=connection,
                        sources=self.sources,
                        initial_dest_path=self.dest_path,
                    )
        else:
            window = ConnectionsWindow(self)

        self.present_window(window)

    def send_desktop_notification(self, title: str, body: str) -> None:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        self.send_notification(None, notification)

    def present_window(self, window: Gtk.Window) -> None:
        LOGGER.info("Presenting window %s", type(window).__name__)
        self._child_windows.add(window)
        window.connect("close-request", self._on_window_close_request)
        window.present()

    def _on_window_close_request(self, window: Gtk.Window) -> bool:
        LOGGER.info("Closing window %s", type(window).__name__)
        self._child_windows.discard(window)
        return False


class ConnectionsWindow(Adw.ApplicationWindow):
    def __init__(self, app: RsyncExtApplication, status_message: str | None = None) -> None:
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(820, 560)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_wrap(True)
        self.status_label.add_css_class("dim-label")

        self.dependencies_label = Gtk.Label(xalign=0)
        self.dependencies_label.set_wrap(True)

        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")

        add_button = Gtk.Button(label="Add Connection")
        add_button.connect("clicked", self.on_add_clicked)

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_margin_top(18)
        container.set_margin_bottom(18)
        container.set_margin_start(18)
        container.set_margin_end(18)

        intro = Gtk.Label(
            label="Saved servers for sending local files and folders with rsync over SSH.",
            xalign=0,
        )
        intro.set_wrap(True)
        container.append(intro)
        container.append(self.dependencies_label)
        container.append(self.status_label)

        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(self.list_box)
        container.append(scroll)
        self.set_content(
            _toolbar_content(
                container,
                end_widgets=[refresh_button, add_button],
            )
        )

        if status_message:
            self.set_status(status_message)

        self.refresh()

    @property
    def app(self) -> RsyncExtApplication:
        return self.get_application()

    def set_status(self, message: str, *, is_error: bool = False) -> None:
        self.status_label.set_text(message)
        if is_error:
            self.status_label.add_css_class("error")
        else:
            self.status_label.remove_css_class("error")

    def refresh(self) -> None:
        while True:
            row = self.list_box.get_first_child()
            if row is None:
                break
            self.list_box.remove(row)

        dependency_summary = []
        for status in check_dependencies():
            if status.available:
                dependency_summary.append(f"{status.name}: ok")
            else:
                dependency_summary.append(f"{status.name}: missing ({status.required_for})")
        self.dependencies_label.set_text("Dependencies: " + " | ".join(dependency_summary))

        connections = self.app.store.load()
        if not connections:
            placeholder = Gtk.Label(
                label="No saved connections yet. Add one to get a 'Send to Server' entry in Files.",
                xalign=0,
            )
            placeholder.set_wrap(True)
            self.list_box.append(placeholder)
            return

        for connection in connections:
            self.list_box.append(ConnectionRow(self, connection))

    def on_add_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Add Connection clicked")
        self.app.present_window(ConnectionEditorWindow(self))

    def on_refresh_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Refresh clicked")
        self.refresh()
        self.set_status("Connection list refreshed.")


class ConnectionRow(Gtk.ListBoxRow):
    def __init__(self, parent: ConnectionsWindow, connection: Connection) -> None:
        super().__init__()
        self.parent_window = parent
        self.connection = connection

        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        row_box.set_margin_top(12)
        row_box.set_margin_bottom(12)
        row_box.set_margin_start(12)
        row_box.set_margin_end(12)

        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title = Gtk.Label(label=connection.label, xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)

        self.enabled_switch = Gtk.Switch(active=connection.enabled, valign=Gtk.Align.CENTER)
        self.enabled_switch.connect("notify::active", self.on_enabled_toggled)

        title_box.append(title)
        title_box.append(Gtk.Label(label="Enabled", xalign=1))
        title_box.append(self.enabled_switch)

        subtitle = Gtk.Label(
            label=self._summary(connection),
            xalign=0,
        )
        subtitle.set_wrap(True)
        subtitle.add_css_class("dim-label")

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        test_button = Gtk.Button(label="Test")
        test_button.connect("clicked", self.on_test_clicked)
        edit_button = Gtk.Button(label="Edit")
        edit_button.connect("clicked", self.on_edit_clicked)
        delete_button = Gtk.Button(label="Delete")
        delete_button.connect("clicked", self.on_delete_clicked)

        buttons.append(test_button)
        buttons.append(edit_button)
        buttons.append(delete_button)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_wrap(True)
        self.status_label.add_css_class("caption")

        row_box.append(title_box)
        row_box.append(subtitle)
        row_box.append(buttons)
        row_box.append(self.status_label)
        self.set_child(row_box)

    def _summary(self, connection: Connection) -> str:
        auth = "Password" if connection.auth_type == "password" else "SSH key"
        return (
            f"{connection.username}@{connection.host}:{connection.port} | "
            f"{auth} | default path {connection.default_destination_path}"
        )

    def on_enabled_toggled(self, switch: Gtk.Switch, _param: object) -> None:
        self.connection.enabled = switch.get_active()
        self.parent_window.app.store.upsert(self.connection)
        state = "enabled" if self.connection.enabled else "disabled"
        self.status_label.set_text(f"Connection {state}.")

    def on_edit_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Edit clicked for connection_id=%s", self.connection.id)
        self.parent_window.app.present_window(
            ConnectionEditorWindow(self.parent_window, connection=self.connection)
        )

    def on_delete_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Delete clicked for connection_id=%s", self.connection.id)
        self.parent_window.app.store.delete(self.connection.id)
        self.parent_window.app.secret_store.clear_password(self.connection.id)
        self.parent_window.refresh()
        self.parent_window.set_status(f"Deleted '{self.connection.label}'.")

    def on_test_clicked(self, button: Gtk.Button) -> None:
        LOGGER.info("Test clicked for connection_id=%s", self.connection.id)
        button.set_sensitive(False)
        self.status_label.set_text("Testing connection...")

        def worker() -> None:
            try:
                test_connection(self.connection, secret_store=self.parent_window.app.secret_store)
            except Exception as exc:
                LOGGER.exception("Connection test failed for connection_id=%s", self.connection.id)
                GLib.idle_add(self._finish_test, button, False, str(exc))
            else:
                LOGGER.info("Connection test succeeded for connection_id=%s", self.connection.id)
                GLib.idle_add(self._finish_test, button, True, "Connection succeeded.")

        threading.Thread(target=worker, daemon=True).start()

    def _finish_test(self, button: Gtk.Button, success: bool, message: str) -> bool:
        button.set_sensitive(True)
        self.status_label.set_text(message)
        if success:
            self.parent_window.app.send_desktop_notification(
                "Connection test succeeded",
                self.connection.label,
            )
        return False


class ConnectionEditorWindow(Adw.Window):
    def __init__(
        self,
        parent: ConnectionsWindow,
        connection: Connection | None = None,
    ) -> None:
        super().__init__(
            application=parent.app,
            title="Edit Connection" if connection else "Add Connection",
            transient_for=parent,
            modal=True,
        )
        self.parent_window = parent
        self.connection = connection
        self.secret_store = parent.app.secret_store
        self.set_default_size(520, 520)

        save_button = Gtk.Button(label="Save")
        save_button.connect("clicked", self.on_save_clicked)

        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda _button: self.close())

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_wrap(True)

        self.label_entry = Gtk.Entry(text=connection.label if connection else "")
        self.host_entry = Gtk.Entry(text=connection.host if connection else "")
        self.port_entry = Gtk.Entry(text=str(connection.port if connection else 22))
        self.user_entry = Gtk.Entry(text=connection.username if connection else "")

        self.auth_combo = Gtk.DropDown.new_from_strings(["password", "ssh_key"])
        if connection and connection.auth_type == "ssh_key":
            self.auth_combo.set_selected(1)

        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)

        self.key_entry = Gtk.Entry(text=connection.private_key_path if connection else "")
        self.key_entry.set_editable(False)
        self.key_entry.set_hexpand(True)
        self.dest_entry = Gtk.Entry(
            text=connection.default_destination_path if connection else "~/"
        )
        self.enabled_switch = Gtk.Switch(active=connection.enabled if connection else True)
        self.pick_key_button = Gtk.Button(label="Browse...")
        self.pick_key_button.connect("clicked", self.on_pick_key_clicked)
        self.clear_key_button = Gtk.Button(label="Clear")
        self.clear_key_button.connect("clicked", self.on_clear_key_clicked)

        self.auth_combo.connect("notify::selected", self.on_auth_changed)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        form.set_margin_top(18)
        form.set_margin_bottom(18)
        form.set_margin_start(18)
        form.set_margin_end(18)

        for title, widget in [
            ("Label", self.label_entry),
            ("Host / IP", self.host_entry),
            ("Port", self.port_entry),
            ("Username", self.user_entry),
            ("Auth Type", self.auth_combo),
            (
                "Password" if not connection else "Password (leave blank to keep current)",
                self.password_entry,
            ),
            ("Default Destination Path", self.dest_entry),
        ]:
            form.append(_field_row(title, widget))
        form.append(
            _field_row(
                "Private Key Path",
                _inline_widget_row(
                    self.key_entry,
                    self.pick_key_button,
                    self.clear_key_button,
                ),
            )
        )
        form.append(_compact_field_row("Enabled", self.enabled_switch))

        form.append(self.status_label)
        self.set_content(
            _toolbar_content(
                form,
                start_widgets=[cancel_button],
                end_widgets=[save_button],
            )
        )
        self.on_auth_changed(self.auth_combo, None)

    def on_auth_changed(self, _combo: Gtk.DropDown, _param: object | None) -> None:
        auth_type = self.auth_combo.get_selected_item().get_string()
        self.password_entry.set_sensitive(auth_type == "password")
        self.key_entry.set_sensitive(auth_type == "ssh_key")
        self.pick_key_button.set_sensitive(auth_type == "ssh_key")
        self.clear_key_button.set_sensitive(auth_type == "ssh_key")

    def on_pick_key_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Private key picker opened")
        chooser = Gtk.FileChooserNative(
            title="Select Private Key",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Select",
            cancel_label="Cancel",
        )
        chooser.connect("response", self.on_pick_key_response)

        current_path = self.key_entry.get_text().strip()
        if current_path:
            current_file = Gio.File.new_for_path(current_path)
            chooser.set_file(current_file)

        chooser.show()

    def on_pick_key_response(self, chooser: Gtk.FileChooserNative, response: int) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            selected = chooser.get_file()
            if selected is not None:
                path = selected.get_path()
                if path:
                    LOGGER.info("Private key selected: %s", path)
                    self.key_entry.set_text(path)
        chooser.destroy()

    def on_clear_key_clicked(self, _button: Gtk.Button) -> None:
        self.key_entry.set_text("")

    def on_save_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Save connection clicked existing=%s", self.connection is not None)
        try:
            auth_type = self.auth_combo.get_selected_item().get_string()
            connection = Connection(
                id=self.connection.id if self.connection else new_connection_id(),
                label=self.label_entry.get_text().strip(),
                host=self.host_entry.get_text().strip(),
                port=int(self.port_entry.get_text().strip() or "22"),
                username=self.user_entry.get_text().strip(),
                auth_type=auth_type,
                private_key_path=self.key_entry.get_text().strip() or None,
                default_destination_path=self.dest_entry.get_text().strip(),
                enabled=self.enabled_switch.get_active(),
            )
            connection.validate()
            self.parent_window.app.store.upsert(connection)
            if auth_type == "password":
                password = self.password_entry.get_text()
                if not password and self.connection is None:
                    raise ValueError("Password is required for a new password-based connection.")
                if password:
                    self.secret_store.set_password(connection.id, password)
            else:
                self.secret_store.clear_password(connection.id)
        except Exception as exc:
            LOGGER.exception("Saving connection failed")
            self.status_label.set_text(str(exc))
            return

        LOGGER.info("Connection saved id=%s label=%s", connection.id, connection.label)
        self.parent_window.refresh()
        self.parent_window.set_status(f"Saved '{connection.label}'.")
        self.close()


class SendWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        app: RsyncExtApplication,
        *,
        connection: Connection,
        sources: list[str],
        initial_dest_path: str | None,
    ) -> None:
        super().__init__(application=app, title="Send to Server")
        self.connection = connection
        self.sources = sources
        self.set_default_size(700, 460)

        start_button = Gtk.Button(label="Start Transfer")
        start_button.connect("clicked", self.on_start_clicked)

        manage_button = Gtk.Button(label="Manage Connections")
        manage_button.connect("clicked", self.on_manage_clicked)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_wrap(True)

        self.dest_entry = Gtk.Entry(
            text=initial_dest_path or connection.default_destination_path,
        )
        self.disable_unix_attrs_switch = Gtk.Switch(active=True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        summary = Gtk.Label(
            label=(
                f"Destination: {connection.label} "
                f"({connection.username}@{connection.host}:{connection.port})"
            ),
            xalign=0,
        )
        summary.set_wrap(True)
        root.append(summary)
        root.append(_field_row("Destination Path", self.dest_entry))
        root.append(
            _compact_field_row(
                "Disable Unix perms/owner/group",
                self.disable_unix_attrs_switch,
            )
        )

        sources_label = Gtk.Label(label="Selected Sources", xalign=0)
        root.append(sources_label)

        self.sources_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        self.sources_view.get_buffer().set_text("\n".join(sources))
        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_child(self.sources_view)
        root.append(scroller)
        root.append(self.status_label)

        self.set_content(
            _toolbar_content(
                root,
                start_widgets=[manage_button],
                end_widgets=[start_button],
            )
        )

        if not sources:
            self.status_label.set_text("No local files were selected.")

    def on_manage_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Manage Connections clicked from SendWindow")
        try:
            app = self.get_application()
            if app is None:
                raise RuntimeError("Application instance is unavailable.")
            app.present_window(ConnectionsWindow(app))
        except Exception:
            LOGGER.exception("Manage Connections failed from SendWindow")
            self.status_label.set_text("Failed to open Manage Connections. See the log file.")
            return
        self.close()

    def on_start_clicked(self, _button: Gtk.Button) -> None:
        LOGGER.info("Start Transfer clicked for connection_id=%s", self.connection.id)
        if not self.sources:
            self.status_label.set_text("No local files were selected.")
            return

        try:
            window = TransferWindow(
                self.get_application(),
                connection=self.connection,
                sources=self.sources,
                dest_path=self.dest_entry.get_text().strip(),
                preserve_unix_attrs=not self.disable_unix_attrs_switch.get_active(),
            )
        except Exception as exc:
            LOGGER.exception("Preparing transfer window failed")
            self.status_label.set_text(str(exc))
            return

        app = self.get_application()
        if app is None:
            self.status_label.set_text("Application instance is unavailable.")
            return
        app.present_window(window)
        self.close()


class TransferWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        app: RsyncExtApplication,
        *,
        connection: Connection,
        sources: list[str],
        dest_path: str,
        preserve_unix_attrs: bool,
    ) -> None:
        super().__init__(application=app, title="Transfer Progress")
        self.connection = connection
        self.sources = sources
        self.dest_path = dest_path
        self.preserve_unix_attrs = preserve_unix_attrs
        self.set_default_size(780, 520)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_wrap(True)
        self.status_label.set_text("Preparing transfer...")

        self.output_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        self.output_buffer = self.output_view.get_buffer()

        close_button = Gtk.Button(label="Close")
        close_button.set_sensitive(False)
        close_button.connect("clicked", lambda _button: self.close())
        self.close_button = close_button

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_child(self.output_view)
        root.append(self.status_label)
        root.append(scroller)
        self.set_content(_toolbar_content(root, end_widgets=[close_button]))

        self.start_transfer()

    @property
    def app(self) -> RsyncExtApplication:
        return self.get_application()

    def start_transfer(self) -> None:
        LOGGER.info("Transfer thread starting for connection_id=%s", self.connection.id)
        def worker() -> None:
            try:
                plan = build_transfer_plan(
                    self.connection,
                    self.sources,
                    self.dest_path,
                    accept_new_hostkey=True,
                    preserve_unix_attrs=self.preserve_unix_attrs,
                    secret_store=self.app.secret_store,
                )
            except Exception as exc:
                LOGGER.exception("Building transfer plan failed")
                GLib.idle_add(self._finish, False, str(exc), "")
                return

            output_lines: list[str] = []
            try:
                process = subprocess.Popen(
                    plan.command,
                    env=plan.env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except FileNotFoundError as exc:
                LOGGER.exception("Starting transfer process failed")
                GLib.idle_add(self._finish, False, f"Failed to start transfer: {exc}", "")
                return

            GLib.idle_add(
                self.status_label.set_text,
                f"Sending to {plan.remote_target}",
            )

            assert process.stdout is not None
            for line in process.stdout:
                output_lines.append(line)
                GLib.idle_add(self._append_output, line)

            returncode = process.wait()
            combined = "".join(output_lines)
            if returncode == 0:
                LOGGER.info("Transfer succeeded for connection_id=%s", self.connection.id)
                GLib.idle_add(self._finish, True, "Transfer completed successfully.", combined)
                return

            initial_result = CommandResult(
                returncode=returncode,
                stdout=combined,
                stderr=combined,
            )
            if should_retry_with_inplace(initial_result):
                retry_notice = (
                    "Destination rejected temporary rsync files; retrying with in-place writes...\n"
                )
                output_lines.append(retry_notice)
                GLib.idle_add(self._append_output, retry_notice)
                try:
                    retry_plan = build_transfer_plan(
                        self.connection,
                        self.sources,
                        self.dest_path,
                        accept_new_hostkey=True,
                        use_inplace=True,
                        preserve_unix_attrs=self.preserve_unix_attrs,
                        secret_store=self.app.secret_store,
                    )
                    retry_process = subprocess.Popen(
                        retry_plan.command,
                        env=retry_plan.env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                except Exception as exc:
                    GLib.idle_add(self._finish, False, str(exc), combined)
                    return

                assert retry_process.stdout is not None
                retry_output_lines: list[str] = []
                for line in retry_process.stdout:
                    retry_output_lines.append(line)
                    GLib.idle_add(self._append_output, line)

                retry_returncode = retry_process.wait()
                retry_combined = "".join(retry_output_lines)
                if retry_returncode == 0:
                    LOGGER.info(
                        "Transfer succeeded after inplace retry for connection_id=%s",
                        self.connection.id,
                    )
                    GLib.idle_add(
                        self._finish,
                        True,
                        "Transfer completed successfully.",
                        combined + retry_notice + retry_combined,
                    )
                    return

                combined = combined + retry_notice + retry_combined
                returncode = retry_returncode

            error = map_command_error(
                CommandResult(returncode=returncode, stdout=combined, stderr=combined)
            )
            LOGGER.error(
                "Transfer failed for connection_id=%s returncode=%s details=%s",
                self.connection.id,
                returncode,
                error.details,
            )
            GLib.idle_add(self._finish, False, str(error), error.details)

        threading.Thread(target=worker, daemon=True).start()

    def _append_output(self, line: str) -> bool:
        end = self.output_buffer.get_end_iter()
        self.output_buffer.insert(end, line)
        self.status_label.set_text(line.strip() or self.status_label.get_text())
        return False

    def _finish(self, success: bool, message: str, details: str) -> bool:
        self.status_label.set_text(message)
        if details and not success:
            end = self.output_buffer.get_end_iter()
            self.output_buffer.insert(end, details + "\n")
        self.close_button.set_sensitive(True)
        title = "Transfer finished" if success else "Transfer failed"
        self.app.send_desktop_notification(title, message)
        return False


def _field_row(title: str, widget: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    label = Gtk.Label(label=title, xalign=0)
    box.append(label)
    box.append(widget)
    return box


def _compact_field_row(title: str, widget: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    label = Gtk.Label(label=title, xalign=0)
    label.set_hexpand(True)
    box.append(label)
    box.append(widget)
    return box


def _inline_widget_row(*widgets: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    for widget in widgets:
        box.append(widget)
    return box


def _toolbar_content(
    content: Gtk.Widget,
    *,
    start_widgets: list[Gtk.Widget] | None = None,
    end_widgets: list[Gtk.Widget] | None = None,
) -> Adw.ToolbarView:
    header = Adw.HeaderBar()
    for widget in start_widgets or []:
        header.pack_start(widget)
    for widget in end_widgets or []:
        header.pack_end(widget)

    view = Adw.ToolbarView()
    view.add_top_bar(header)
    view.set_content(content)
    return view
