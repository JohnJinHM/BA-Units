#!/usr/bin/env python3
"""
Broken Arrow extractor — simple desktop UI.

Pick an *export* (what you want to produce) and the panel below shows exactly
the *source files* that export needs to import, plus that tool's CLI flags as
editable widgets. "Run" shells out to the matching tools/ script(s) with the
flags you chose and streams the output, so the GUI stays a thin front-end over
the same scripts the README documents — no logic is duplicated here.

"Extract All" is the default: point it at a normal AssetRipper ExportedProject
folder and it runs the database, localization and manifest extractors in one go.

    python tools/gui.py
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, ttk, scrolledtext

TOOLS_DIR = Path(__file__).resolve().parent

# Kinds: "file"/"dir" add a Browse button, "text"/"int" are entries, "flag" is a
# checkbox (store_true). Empty text/int values are simply not passed, so the
# script's own default applies.
FILE, DIR, TEXT, INT, FLAG = "file", "dir", "text", "int", "flag"


@dataclass
class Field:
    flag: str           # CLI flag, e.g. "--asset"
    label: str
    kind: str
    default: object = ""
    patterns: str = "*.*"   # file dialog filter, e.g. "*.asset"


@dataclass
class Export:
    name: str
    script: str            # tools/ script for single-command exports ("" if plan is set)
    blurb: str
    fields: list[Field] = field(default_factory=list)
    # Optional override: map the current field values to a list of
    # (script, args) commands run in order. Used by multi-step exports.
    plan: Callable[[dict[str, str]], list[tuple[str, list[str]]]] | None = None


def _extract_all(v: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Derive the three extractor commands from one ExportedProject folder."""
    root, out = v["--root"], v["--out"]
    return [
        ("extract_database.py",
         ["--asset", f"{root}/Assets/Resources/DataBaseCompiled.asset", "--out", out, "--combined"]),
        ("extract_localization.py",
         ["--text-dir", f"{root}/Assets/TextAsset", "--out", f"{out}/localization"]),
        ("extract_manifest.py", ["--root", root, "--out", out]),
    ]


EXPORTS = [
    Export(
        "Extract All (ExportedProject)",
        "",
        "Run the database, localization and manifest extractors from one export folder.",
        [
            Field("--root", "ExportedProject folder", DIR, "ExportedProject"),
            Field("--out", "Output folder", DIR, "output"),
        ],
        plan=_extract_all,
    ),
    Export(
        "Unit Database",
        "extract_database.py",
        "Decrypt DataBaseCompiled.asset → output/tables/*.json.",
        [
            Field("--asset", "Encrypted unit DB", FILE,
                  "ExportedProject/Assets/Resources/DataBaseCompiled.asset", "*.asset"),
            Field("--out", "Output folder", DIR, "output"),
            Field("--key", "AES key", TEXT, "09234237536700238099172758697347"),
            Field("--marker", "Marker", TEXT, "fhk3s0g3"),
            Field("--indent", "JSON indent (0 = compact)", INT, "2"),
            Field("--combined", "Also write combined database.json", FLAG, True),
        ],
    ),
    Export(
        "Localization",
        "extract_localization.py",
        "Zip keys.json + <lang>.json into flat { key: text } maps.",
        [
            Field("--text-dir", "Folder with keys.json + <lang>.json", DIR,
                  "ExportedProject/Assets/TextAsset"),
            Field("--out", "Output folder", DIR, "output/localization"),
            Field("--lang", "Language code", TEXT, "eng"),
            Field("--all", "Export every available language", FLAG, False),
        ],
    ),
    Export(
        "Manifest",
        "extract_manifest.py",
        "Read build provenance (version, Unity, source hash) from ProjectSettings.",
        [
            Field("--root", "ExportedProject folder", DIR, "ExportedProject"),
            Field("--out", "Output folder", DIR, "output"),
            Field("--game-version", "Game version override (optional)", TEXT),
        ],
    ),
    Export(
        "AES Key Recovery",
        "recover_key.py",
        "Recover the AES key + marker from native code after a patch.",
        [
            Field("--dll", "GameAssembly.dll", FILE, "GameAssembly.dll", "*.dll"),
            Field("--script", "Il2CppDumper script.json", FILE, "script.json", "*.json"),
            Field("--out", "Write key.json to (optional)", FILE, "", "*.json"),
        ],
    ),
]


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.log_q: queue.Queue[str | None] = queue.Queue()
        root.title("Broken Arrow — Extractor")
        root.geometry("720x620")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # Export picker.
        top = ttk.Frame(root, padding=10)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Export asset:").pack(side="left")
        self.choice = StringVar(value=EXPORTS[0].name)
        picker = ttk.Combobox(top, textvariable=self.choice, state="readonly",
                              values=[e.name for e in EXPORTS], width=24)
        picker.pack(side="left", padx=8)
        picker.bind("<<ComboboxSelected>>", lambda _e: self.render_fields())
        self.run_btn = ttk.Button(top, text="Run", command=self.run)
        self.run_btn.pack(side="right")

        self.blurb = ttk.Label(root, padding=(10, 0), foreground="#555")
        self.blurb.grid(row=1, column=0, sticky="ew")

        # Source files + flags for the current export.
        self.form = ttk.LabelFrame(root, text="Source files & options", padding=10)
        self.form.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        self.form.columnconfigure(1, weight=1)

        self.log = scrolledtext.ScrolledText(root, height=12, state="disabled",
                                             font=("Consolas", 9))
        self.log.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        root.rowconfigure(3, weight=1)

        self.vars: dict[str, StringVar | BooleanVar] = {}
        self.render_fields()
        root.after(100, self._drain_log)

    @property
    def export(self) -> Export:
        return next(e for e in EXPORTS if e.name == self.choice.get())

    def render_fields(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        self.blurb.config(text=self.export.blurb)

        for row, f in enumerate(self.export.fields):
            if f.kind == FLAG:
                var = BooleanVar(value=bool(f.default))
                ttk.Checkbutton(self.form, text=f.label, variable=var).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=3)
            else:
                var = StringVar(value=str(f.default))
                ttk.Label(self.form, text=f.label).grid(row=row, column=0, sticky="w", pady=3)
                ttk.Entry(self.form, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6)
                if f.kind in (FILE, DIR):
                    ttk.Button(self.form, text="Browse…",
                               command=lambda fl=f, v=var: self._browse(fl, v)).grid(
                        row=row, column=2)
            self.vars[f.flag] = var

    def _browse(self, f: Field, var: StringVar) -> None:
        if f.kind == DIR:
            path = filedialog.askdirectory(title=f.label)
        else:
            path = filedialog.askopenfilename(
                title=f.label, filetypes=[(f.label, f.patterns), ("All files", "*.*")])
        if path:
            var.set(path)

    def build_args(self) -> list[str]:
        args: list[str] = []
        for f in self.export.fields:
            var = self.vars[f.flag]
            if f.kind == FLAG:
                if var.get():
                    args.append(f.flag)
            else:
                value = str(var.get()).strip()
                if value:
                    args += [f.flag, value]
        return args

    def commands(self) -> list[tuple[str, list[str]]]:
        """The (script, args) command(s) to run for the current export."""
        e = self.export
        if e.plan:
            values = {f.flag: str(self.vars[f.flag].get()).strip() for f in e.fields}
            return e.plan(values)
        return [(e.script, self.build_args())]

    def run(self) -> None:
        self.run_btn.config(state="disabled")
        self._write("", clear=True)
        threading.Thread(target=self._worker, args=(self.commands(),), daemon=True).start()

    def _worker(self, commands: list[tuple[str, list[str]]]) -> None:
        try:
            for script, args in commands:
                argv = [sys.executable, str(TOOLS_DIR / script), *args]
                self.log_q.put(f"$ {' '.join(argv)}\n")
                proc = subprocess.Popen(
                    argv, cwd=TOOLS_DIR.parent, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1)
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.log_q.put(line)
                self.log_q.put(f"[exit {proc.wait()}]\n\n")
        except Exception as exc:  # noqa: BLE001 - surface any launch error in the log
            self.log_q.put(f"[failed to run: {exc}]\n")
        self.log_q.put(None)  # sentinel: re-enable the Run button

    def _drain_log(self) -> None:
        try:
            while True:
                item = self.log_q.get_nowait()
                if item is None:
                    self.run_btn.config(state="normal")
                else:
                    self._write(item)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    def _write(self, text: str, clear: bool = False) -> None:
        self.log.config(state="normal")
        if clear:
            self.log.delete("1.0", "end")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")


def main() -> None:
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
