from __future__ import annotations

import argparse
import os
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog
from tkinter import ttk
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gui.combobox_compat import (
    GuiDisplayRuntime,
    WaylandComboboxPopup,
    detect_gui_display_runtime,
    enable_wayland_combobox_support,
    resolve_linux_combobox_policy,
)


@dataclass(slots=True)
class ComboScenario:
    name: str
    state: str
    values: tuple[str, ...]
    bind_down: bool = True


class ComboboxDebuggerApp:
    def __init__(self, *, mode: str, bind_down: bool) -> None:
        self.root = tk.Tk()
        self.root.title("Wayland Combobox Debugger")
        self.root.geometry("1180x860")
        self.root.minsize(980, 720)
        self.mode_var = tk.StringVar(value=mode)
        self.bind_down_var = tk.BooleanVar(value=bind_down)
        self.runtime = detect_gui_display_runtime()
        self.manager_by_widget: dict[ttk.Combobox, WaylandComboboxPopup] = {}
        self.runtime_text: tk.Text | None = None
        self.log_text: tk.Text | None = None
        self.sample_frame: ttk.LabelFrame | None = None
        self._build()

    def _build(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(3, weight=2)

        header = ttk.Frame(self.root, padding=(12, 12, 12, 0))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = ttk.Label(
            header,
            text="Wayland Combobox Debugger",
            font=("Segoe UI", 14, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text=(
                "Use this window to compare native ttk.Combobox behavior against "
                "the custom compatibility popup and collect focus/key event traces."
            ),
            wraplength=920,
            justify="left",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 0))

        controls = ttk.LabelFrame(self.root, text="Controls", padding=12)
        controls.grid(row=1, column=0, sticky="ew", padx=12, pady=(12, 0))
        controls.grid_columnconfigure(7, weight=1)

        ttk.Label(controls, text="Popup mode").grid(row=0, column=0, sticky="w")
        for index, (label, value) in enumerate(
            (
                ("Auto runtime", "auto"),
                ("Native ttk", "native"),
                ("Force compat", "compat"),
            ),
            start=1,
        ):
            ttk.Radiobutton(
                controls,
                text=label,
                value=value,
                variable=self.mode_var,
                command=self.rebuild_samples,
            ).grid(row=0, column=index, sticky="w", padx=(8, 0))

        ttk.Checkbutton(
            controls,
            text="Compat popup handles plain Down",
            variable=self.bind_down_var,
            command=self.rebuild_samples,
        ).grid(row=0, column=4, sticky="w", padx=(16, 0))

        ttk.Button(controls, text="Rebuild samples", command=self.rebuild_samples).grid(
            row=0,
            column=5,
            sticky="w",
            padx=(16, 0),
        )
        ttk.Button(controls, text="Open modal dialog", command=self.open_modal_dialog).grid(
            row=0,
            column=6,
            sticky="w",
            padx=(8, 0),
        )
        ttk.Button(controls, text="Export log", command=self.export_log).grid(
            row=0,
            column=7,
            sticky="w",
            padx=(8, 0),
        )
        ttk.Button(controls, text="Clear log", command=self.clear_log).grid(
            row=0,
            column=8,
            sticky="e",
        )

        runtime_frame = ttk.LabelFrame(self.root, text="Runtime", padding=12)
        runtime_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(12, 0))
        runtime_frame.grid_columnconfigure(0, weight=1)
        runtime_frame.grid_rowconfigure(0, weight=1)
        runtime_text = tk.Text(runtime_frame, height=10, wrap="word")
        runtime_text.grid(row=0, column=0, sticky="nsew")
        self.runtime_text = runtime_text
        self._refresh_runtime_text()

        bottom = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        bottom.grid(row=3, column=0, sticky="nsew", padx=12, pady=12)

        sample_frame = ttk.LabelFrame(bottom, text="Sample widgets", padding=12)
        sample_frame.grid_columnconfigure(1, weight=1)
        self.sample_frame = sample_frame
        bottom.add(sample_frame, weight=3)

        log_frame = ttk.LabelFrame(bottom, text="Event log", padding=12)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        log_text = tk.Text(log_frame, wrap="word")
        log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text = log_text
        bottom.add(log_frame, weight=4)

        self.rebuild_samples()

    def _refresh_runtime_text(self) -> None:
        runtime_text = self.runtime_text
        if runtime_text is None:
            return
        runtime_text.configure(state="normal")
        runtime_text.delete("1.0", tk.END)
        lines = self._runtime_lines()
        runtime_text.insert("1.0", "\n".join(lines))
        runtime_text.configure(state="disabled")

    def _runtime_lines(self) -> list[str]:
        tk_patchlevel = str(self.root.tk.call("info", "patchlevel"))
        windowing_system = str(self.root.tk.call("tk", "windowingsystem"))
        resolved_policy = resolve_linux_combobox_policy(
            self.runtime,
            tk_windowingsystem=windowing_system,
        )
        return [
            f"platform={sys.platform}",
            f"tk_patchlevel={tk_patchlevel}",
            f"tk_windowingsystem={windowing_system}",
            f"runtime.is_linux={self.runtime.is_linux}",
            f"runtime.is_wayland_native={self.runtime.is_wayland_native}",
            f"runtime.is_xwayland={self.runtime.is_xwayland}",
            f"resolved_policy={resolved_policy}",
            f"env.XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '')}",
            f"env.WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', '')}",
            f"env.DISPLAY={os.environ.get('DISPLAY', '')}",
            f"selected_mode={self.mode_var.get()}",
            f"bind_down={self.bind_down_var.get()}",
            "",
            *self._probe_lines(),
        ]

    def _probe_lines(self) -> list[str]:
        sample_values = ("Alpha", "Beta", "Gamma")
        probe_combo = ttk.Combobox(self.root, values=sample_values, state="readonly")
        lines = [
            "probe.native_combobox:",
            f"  widget={probe_combo}",
            f"  values={sample_values!r}",
        ]
        try:
            popdown = str(self.root.tk.call("ttk::combobox::PopdownWindow", str(probe_combo)))
            lines.append(f"  popdown_window={popdown}")
            try:
                exists = bool(int(self.root.tk.call("winfo", "exists", popdown)))
            except tk.TclError:
                exists = False
            lines.append(f"  popdown_exists={exists}")
        except tk.TclError as exc:
            lines.append(f"  popdown_window_error={exc}")
        finally:
            probe_combo.destroy()
        return lines

    def rebuild_samples(self) -> None:
        sample_frame = self.sample_frame
        if sample_frame is None:
            return
        for child in sample_frame.winfo_children():
            child.destroy()
        self.manager_by_widget.clear()
        self._refresh_runtime_text()
        self.log(
            "rebuild_samples",
            detail=f"mode={self.mode_var.get()} bind_down={self.bind_down_var.get()}",
        )

        scenarios = (
            ComboScenario(
                name="Readonly combobox",
                state="readonly",
                values=("Alpha", "Beta", "Gamma", "Delta"),
            ),
            ComboScenario(
                name="Normal combobox",
                state="normal",
                values=("Travel", "Food", "Salary", "Utilities"),
            ),
            ComboScenario(
                name="Long readonly combobox",
                state="readonly",
                values=tuple(f"Option {index}" for index in range(1, 19)),
            ),
        )

        instructions = ttk.Label(
            sample_frame,
            text=(
                "Try mouse open, Alt+Down, F4, Down, Escape, Tab, selection, focus transfer, "
                "and popup behavior near window edges."
            ),
            wraplength=420,
            justify="left",
        )
        instructions.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        for row_index, scenario in enumerate(scenarios, start=1):
            self._build_scenario_row(sample_frame, row_index, scenario)

        filler = ttk.Entry(sample_frame)
        filler.grid(row=len(scenarios) + 1, column=1, sticky="ew", pady=(12, 0))
        filler.insert(0, "Focus target for Tab / focus-out tests")
        self._bind_widget_events("focus_target", filler)

    def _build_scenario_row(
        self,
        parent: ttk.LabelFrame,
        row_index: int,
        scenario: ComboScenario,
    ) -> None:
        ttk.Label(parent, text=scenario.name).grid(row=row_index, column=0, sticky="w", pady=6)
        variable = tk.StringVar(value=scenario.values[0])
        combo = ttk.Combobox(
            parent,
            state=scenario.state,
            values=scenario.values,
            textvariable=variable,
        )
        combo.grid(row=row_index, column=1, sticky="ew", pady=6)
        self._bind_widget_events(scenario.name, combo)
        manager = self._attach_popup_mode(
            combo, bind_down=scenario.bind_down and self.bind_down_var.get()
        )
        if manager is not None:
            self._instrument_manager(scenario.name, manager)
        ttk.Button(
            parent,
            text="Focus",
            command=combo.focus_set,
        ).grid(row=row_index, column=2, sticky="w", padx=(12, 0))

    def _attach_popup_mode(
        self,
        combo: ttk.Combobox,
        *,
        bind_down: bool,
    ) -> WaylandComboboxPopup | None:
        mode = self.mode_var.get()
        manager: WaylandComboboxPopup | None = None
        if mode == "compat":
            manager = WaylandComboboxPopup(combo, bind_down=bind_down)
        elif mode == "auto":
            manager = enable_wayland_combobox_support(
                combo,
                bind_down=bind_down,
                runtime=self.runtime,
            )
        if manager is not None:
            self.manager_by_widget[combo] = manager
            self.log(
                "attach_popup_manager",
                widget=combo,
                detail=f"mode={mode} bind_down={bind_down}",
            )
        else:
            self.log("attach_native_combobox", widget=combo, detail=f"mode={mode}")
        return manager

    def _instrument_manager(self, label: str, manager: WaylandComboboxPopup) -> None:
        original_open = manager.open_popup
        original_close = manager.close_popup

        def open_with_logging() -> str:
            self.log(f"{label}.open_popup", widget=manager.widget)
            result = original_open()
            self._bind_popup_events(label, manager)
            return result

        def close_with_logging() -> None:
            self.log(f"{label}.close_popup", widget=manager.widget)
            original_close()

        manager.open_popup = open_with_logging  # type: ignore[method-assign]
        manager.close_popup = close_with_logging  # type: ignore[method-assign]

    def _bind_popup_events(self, label: str, manager: WaylandComboboxPopup) -> None:
        popup = manager.popup
        listbox = manager.listbox
        if popup is not None and not getattr(popup, "_debug_bound", False):
            setattr(popup, "_debug_bound", True)  # noqa: B010
            self._bind_widget_events(f"{label}.popup", popup)
        if listbox is not None and not getattr(listbox, "_debug_bound", False):
            setattr(listbox, "_debug_bound", True)  # noqa: B010
            self._bind_widget_events(f"{label}.listbox", listbox)

    def _bind_widget_events(self, label: str, widget: tk.Misc) -> None:
        events = (
            "<FocusIn>",
            "<FocusOut>",
            "<ButtonPress-1>",
            "<ButtonRelease-1>",
            "<KeyPress>",
            "<KeyRelease>",
            "<Map>",
            "<Unmap>",
            "<<ComboboxSelected>>",
        )
        for sequence in events:
            widget.bind(
                sequence,
                self._make_logger(label, sequence),
                add="+",
            )

    def _make_logger(self, label: str, sequence: str) -> Callable[[tk.Event], None]:
        def _log(event: tk.Event) -> None:
            detail = self._describe_event(event)
            self.log(f"{label} {sequence}", widget=event.widget, detail=detail)

        return _log

    def _describe_event(self, event: tk.Event) -> str:
        parts: list[str] = []
        keysym = getattr(event, "keysym", "")
        char = getattr(event, "char", "")
        x = getattr(event, "x", None)
        y = getattr(event, "y", None)
        if keysym:
            parts.append(f"keysym={keysym}")
        if char:
            parts.append(f"char={char!r}")
        if x is not None and y is not None:
            parts.append(f"xy=({x},{y})")
        if isinstance(event.widget, ttk.Combobox):
            parts.append(f"value={event.widget.get()!r}")
            parts.append(f"state={event.widget.cget('state')!r}")
        return " ".join(parts)

    def log(self, action: str, *, widget: tk.Misc | None = None, detail: str = "") -> None:
        log_text = self.log_text
        if log_text is None:
            return
        stamp = time.strftime("%H:%M:%S")
        widget_name = ""
        if widget is not None:
            widget_name = f" widget={widget.winfo_class()}:{widget}"
        suffix = f" {detail}" if detail else ""
        log_text.insert(tk.END, f"[{stamp}] {action}{widget_name}{suffix}\n")
        log_text.see(tk.END)

    def clear_log(self) -> None:
        log_text = self.log_text
        if log_text is None:
            return
        log_text.delete("1.0", tk.END)
        self.log("clear_log")

    def export_log(self) -> None:
        log_text = self.log_text
        if log_text is None:
            return
        default_name = time.strftime("wayland-combobox-debug-%Y%m%d-%H%M%S.log")
        initial_dir = Path.cwd()
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export debugger log",
            initialdir=str(initial_dir),
            initialfile=default_name,
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not target:
            self.log("export_log_cancelled")
            return
        payload = self._export_payload()
        Path(target).write_text(payload, encoding="utf-8")
        self.log("export_log", detail=target)

    def _export_payload(self) -> str:
        log_text = self.log_text
        log_body = "" if log_text is None else log_text.get("1.0", tk.END).strip()
        sections = [
            "# Runtime",
            *self._runtime_lines(),
            "",
            "# Log",
            log_body,
        ]
        return "\n".join(sections).rstrip() + "\n"

    def open_modal_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Modal Combobox Dialog")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.grid_columnconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text="Use this modal surface to reproduce popup/focus issues inside dialogs.",
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 8))

        ttk.Label(dialog, text="Readonly dialog combobox").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(12, 8),
            pady=8,
        )
        combo = ttk.Combobox(
            dialog,
            values=("Dialog A", "Dialog B", "Dialog C"),
            state="readonly",
        )
        combo.set("Dialog A")
        combo.grid(row=1, column=1, sticky="ew", pady=8, padx=(0, 8))
        self._bind_widget_events("modal.readonly", combo)
        manager = self._attach_popup_mode(combo, bind_down=self.bind_down_var.get())
        if manager is not None:
            self._instrument_manager("modal.readonly", manager)

        ttk.Entry(dialog).grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=8)
        ttk.Button(dialog, text="Close", command=dialog.destroy).grid(
            row=3,
            column=2,
            sticky="e",
            padx=12,
            pady=12,
        )
        self._bind_widget_events("modal.dialog", dialog)
        self.log("open_modal_dialog", widget=dialog)

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wayland Combobox debugger")
    parser.add_argument(
        "--mode",
        choices=("auto", "native", "compat"),
        default="auto",
        help="choose whether sample comboboxes use native ttk, forced compat popup, or runtime auto mode",
    )
    parser.add_argument(
        "--no-bind-down",
        action="store_true",
        help="disable plain Down key popup handling in compat mode",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = ComboboxDebuggerApp(mode=args.mode, bind_down=not args.no_bind_down)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
