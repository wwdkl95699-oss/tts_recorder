#!/usr/bin/env python3
# gui6.py

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import core  # our modular core

CMD_START = "start"
CMD_STOP = "stop"
CMD_PLAY = "play"
CMD_REDO = "redo"
CMD_DELETE = "delete"
CMD_EXIT = "exit"

# -------------------- Worker Thread --------------------
# -------------------- Worker Thread --------------------


class AudioWorker(threading.Thread):
    def __init__(self, cmd_q, evt_q, session_dir, csv_path):
        super().__init__(daemon=True)
        self.cmd_q = cmd_q
        self.evt_q = evt_q
        self.session_dir = session_dir
        self.csv_path = csv_path

        self.recorder = core.DJIRecorder()
        self.validator = core.AudioValidator()

        self.active_line = None
        self.active_wav = None
        self.active_text = None

        self.running = True

    def run(self):
        while self.running:
            try:
                msg = self.cmd_q.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                cmd = msg["cmd"]

                # ---------------- EXIT ----------------
                if cmd == CMD_EXIT:
                    if self.recorder.recording:
                        self.recorder.stop()
                    self.running = False
                    self.evt_q.put({"type": "exit"})
                    return

                # ---------------- START ----------------
                elif cmd == CMD_START:
                    self.active_line = msg["line_index"]
                    self.active_wav = msg["wav"]
                    self.active_text = msg["line"]

                    self.recorder.start(msg["path"])
                    self.evt_q.put({"type": "recording_started"})

                # ---------------- STOP ----------------
                elif cmd == CMD_STOP:
                    if not self.recorder.recording:
                        self.evt_q.put(
                            {"type": "error", "err": "Stop called while not recording"})
                        continue

                    path = self.recorder.stop()

                    if path and os.path.exists(path):
                        metrics = self.validator.analyze(path)
                        ok, reason = self.validator.is_acceptable(metrics)

                        if ok:
                            core.append_recording(
                                self.csv_path,
                                self.active_wav,
                                self.active_text,
                                self.active_line,
                                metrics
                            )
                            self.evt_q.put({"type": "recording_saved"})
                        else:
                            os.remove(path)
                            self.evt_q.put({
                                "type": "recording_rejected",
                                "reason": reason,
                                "metrics": metrics
                            })
                    else:
                        self.evt_q.put(
                            {"type": "error", "err": "Recording failed"})

                    # Clear active state
                    self.active_line = None
                    self.active_wav = None
                    self.active_text = None

                # ---------------- PLAY ----------------
                elif cmd == CMD_PLAY:
                    path = msg["path"]
                    if os.path.exists(path):
                        core.play_audio(path)
                    else:
                        self.evt_q.put(
                            {"type": "error", "err": f"File not found: {path}"})

                # ---------------- REDO ----------------
                elif cmd == CMD_REDO:
                    success = core.remove_last_recording(
                        self.csv_path,
                        self.session_dir,
                        None
                    )
                    self.evt_q.put(
                        {"type": "redo_complete", "success": success})

                # ---------------- DELETE ----------------
                elif cmd == CMD_DELETE:
                    line_idx = msg["line_index"]
                    success = core.delete_recording_by_line(
                        self.csv_path,
                        self.session_dir,
                        line_idx
                    )
                    self.evt_q.put({
                        "type": "line_deleted",
                        "success": success,
                        "line_index": line_idx
                    })

            except Exception as e:
                self.evt_q.put({"type": "error", "err": str(e)})


# -------------------- Settings Dialog --------------------
# -------------------- Settings Dialog --------------------
class SettingsDialog(tk.Toplevel):

    def __init__(self, parent, settings, apply_callback):
        super().__init__(parent)
        self.title("Settings")
        self.settings = settings
        self.apply_callback = apply_callback

        self.transient(parent)
        self.grab_set()

        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Tabs
        files_frame = ttk.Frame(notebook)
        notebook.add(files_frame, text="Files")
        self.build_files_tab(files_frame)

        val_frame = ttk.Frame(notebook)
        notebook.add(val_frame, text="Validation")
        self.build_validation_tab(val_frame)

        dev_frame = ttk.Frame(notebook)
        notebook.add(dev_frame, text="Device")
        self.build_device_tab(dev_frame)

        ui_frame = ttk.Frame(notebook)
        notebook.add(ui_frame, text="UI")
        self.build_ui_tab(ui_frame)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(
            side='left', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side='left', padx=5)

    # -------------------- FILES TAB --------------------

    def build_files_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Script file:").grid(
            row=0, column=0, sticky='w', padx=5, pady=5)
        self.script_var = tk.StringVar(
            value=self.settings.get('files', 'script_file'))
        ttk.Entry(parent, textvariable=self.script_var,
                  width=50).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="Browse...", command=self.browse_script).grid(
            row=0, column=2, padx=5)

        ttk.Label(parent, text="Phonetic map:").grid(
            row=1, column=0, sticky='w', padx=5, pady=5)
        self.map_var = tk.StringVar(
            value=self.settings.get('files', 'map_file'))
        ttk.Entry(parent, textvariable=self.map_var,
                  width=50).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="Browse...", command=self.browse_map).grid(
            row=1, column=2, padx=5)

        ttk.Label(parent, text="Reference dir:").grid(
            row=2, column=0, sticky='w', padx=5, pady=5)
        self.ref_var = tk.StringVar(
            value=self.settings.get('files', 'ref_dir'))
        ttk.Entry(parent, textvariable=self.ref_var,
                  width=50).grid(row=2, column=1, padx=5)
        ttk.Button(parent, text="Browse...", command=self.browse_ref).grid(
            row=2, column=2, padx=5)

    def browse_script(self):
        f = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if f:
            self.script_var.set(f)

    def browse_map(self):
        f = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if f:
            self.map_var.set(f)

    def browse_ref(self):
        d = filedialog.askdirectory()
        if d:
            self.ref_var.set(d)

    # -------------------- VALIDATION TAB --------------------

    def build_validation_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        val = self.settings.get('validation')

        row = 0

        def add_spin(label, var, frm, to, step, unit=""):
            nonlocal row
            ttk.Label(parent, text=label).grid(
                row=row, column=0, sticky='w', padx=8, pady=6)
            ttk.Spinbox(parent,
                        from_=frm,
                        to=to,
                        increment=step,
                        textvariable=var,
                        width=10).grid(row=row, column=1, sticky='w', padx=5)
            if unit:
                ttk.Label(parent, text=unit).grid(
                    row=row, column=2, sticky='w')
            row += 1

        self.min_rms = tk.IntVar(value=val.get('min_rms', 800))
        add_spin("Min RMS:", self.min_rms, 0, 5000, 50)

        self.clip_level = tk.IntVar(value=val.get('clip_level', 30000))
        add_spin("Clip level:", self.clip_level, 10000, 32767, 500)

        self.clip_percent = tk.DoubleVar(value=val.get('clip_percent', 0.5))
        add_spin("Max clip %:", self.clip_percent, 0, 10, 0.1, "%")

        self.cutoff_drop = tk.DoubleVar(
            value=val.get('cutoff_drop_ratio', 0.4))
        add_spin("Cutoff drop ratio:", self.cutoff_drop, 0.1, 0.9, 0.05)

        self.cutoff_win = tk.IntVar(value=val.get('cutoff_window_ms', 200))
        add_spin("Cutoff window:", self.cutoff_win, 50, 1000, 50, "ms")

        self.min_dur = tk.IntVar(value=val.get('min_duration_ms', 600))
        add_spin("Min duration:", self.min_dur, 100, 5000, 100, "ms")

        self.max_dur = tk.IntVar(value=val.get('max_duration_ms', 30000))
        add_spin("Max duration:", self.max_dur, 1000, 60000, 1000, "ms")

    # -------------------- DEVICE TAB --------------------

    def build_device_tab(self, parent):
        dev = self.settings.get('device')

        ttk.Label(parent, text="Preferred keyword:").grid(
            row=0, column=0, sticky='w', padx=5, pady=5)
        self.pref_key = tk.StringVar(value=dev.get('preferred_keyword', ''))
        ttk.Entry(parent, textvariable=self.pref_key).grid(
            row=0, column=1, padx=5)

        ttk.Label(parent, text="Avoid keyword:").grid(
            row=1, column=0, sticky='w', padx=5, pady=5)
        self.avoid_key = tk.StringVar(value=dev.get('avoid_keyword', ''))
        ttk.Entry(parent, textvariable=self.avoid_key).grid(
            row=1, column=1, padx=5)

    # -------------------- UI TAB --------------------

    def build_ui_tab(self, parent):
        ui = self.settings.get('ui')

        ttk.Label(parent, text="Font size:").grid(
            row=0, column=0, sticky='w', padx=5, pady=5)
        self.font_size = tk.IntVar(value=ui.get('font_size', 72))

        ttk.Spinbox(parent,
                    from_=16,
                    to=150,
                    increment=2,
                    textvariable=self.font_size,
                    width=8).grid(row=0, column=1, padx=5)

    # -------------------- SAVE --------------------

    def save(self):
        # Files
        self.settings.set(self.script_var.get(), 'files', 'script_file')
        self.settings.set(self.map_var.get(), 'files', 'map_file')
        self.settings.set(self.ref_var.get(), 'files', 'ref_dir')

        # Validation
        self.settings.set(self.min_rms.get(), 'validation', 'min_rms')
        self.settings.set(self.clip_level.get(), 'validation', 'clip_level')
        self.settings.set(self.clip_percent.get(),
                          'validation', 'clip_percent')
        self.settings.set(self.cutoff_drop.get(),
                          'validation', 'cutoff_drop_ratio')
        self.settings.set(self.cutoff_win.get(),
                          'validation', 'cutoff_window_ms')
        self.settings.set(self.min_dur.get(), 'validation', 'min_duration_ms')
        self.settings.set(self.max_dur.get(), 'validation', 'max_duration_ms')

        # Device
        self.settings.set(self.pref_key.get(), 'device', 'preferred_keyword')
        self.settings.set(self.avoid_key.get(), 'device', 'avoid_keyword')

        # UI
        self.settings.set(self.font_size.get(), 'ui', 'font_size')

        self.settings.save()
        self.apply_callback()
        self.destroy()


def build_validation_tab(self, parent):
    parent.columnconfigure(1, weight=1)
    row = 0
    val = self.settings.get('validation')

    def add_spin(label, var, frm, to, step, unit=""):
        nonlocal row
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky='w', padx=8, pady=6)
        ttk.Spinbox(parent,
                    from_=frm,
                    to=to,
                    increment=step,
                    textvariable=var,
                    width=10).grid(row=row, column=1, sticky='w', padx=5)
        if unit:
            ttk.Label(parent, text=unit).grid(row=row, column=2, sticky='w')
        row += 1

    # RMS
    self.min_rms = tk.IntVar(value=val.get('min_rms', 800))
    add_spin("Min RMS:", self.min_rms, 0, 5000, 50)

    # Clip level
    self.clip_level = tk.IntVar(value=val.get('clip_level', 30000))
    add_spin("Clip level:", self.clip_level, 10000, 32767, 500)

    # Clip percent
    self.clip_percent = tk.DoubleVar(value=val.get('clip_percent', 0.5))
    add_spin("Max clip %:", self.clip_percent, 0, 10, 0.1, "%")

    # Cutoff ratio
    self.cutoff_drop = tk.DoubleVar(value=val.get('cutoff_drop_ratio', 0.4))
    add_spin("Cutoff drop ratio:", self.cutoff_drop, 0.1, 0.9, 0.05)

    # Cutoff window
    self.cutoff_win = tk.IntVar(value=val.get('cutoff_window_ms', 200))
    add_spin("Cutoff window:", self.cutoff_win, 50, 1000, 50, "ms")

    # Min duration
    self.min_dur = tk.IntVar(value=val.get('min_duration_ms', 600))
    add_spin("Min duration:", self.min_dur, 100, 5000, 100, "ms")

    # Max duration (30 sec default)
    self.max_dur = tk.IntVar(value=val.get('max_duration_ms', 30000))
    add_spin("Max duration:", self.max_dur, 1000, 60000, 1000, "ms")

    def build_device_tab(self, parent):
        dev = self.settings.get('device')
        ttk.Label(parent, text="Preferred keyword:").grid(
            row=0, column=0, sticky='w', padx=5, pady=5)
        self.pref_key = tk.StringVar(value=dev['preferred_keyword'])
        ttk.Entry(parent, textvariable=self.pref_key).grid(
            row=0, column=1, padx=5)
        ttk.Label(parent, text="Avoid keyword:").grid(
            row=1, column=0, sticky='w', padx=5, pady=5)
        self.avoid_key = tk.StringVar(value=dev['avoid_keyword'])
        ttk.Entry(parent, textvariable=self.avoid_key).grid(
            row=1, column=1, padx=5)

    # -------------------- UI TAB --------------------

# -------------------- UI TAB --------------------


def build_ui_tab(self, parent):
    ui = self.settings.get('ui')

    ttk.Label(parent, text="Font size:").grid(
        row=0, column=0, sticky='w', padx=5, pady=5
    )

    self.font_size = tk.IntVar(value=ui.get('font_size', 72))

    ttk.Spinbox(
        parent,
        from_=16,
        to=150,
        increment=2,
        textvariable=self.font_size,
        width=8
    ).grid(row=0, column=1, padx=5)

    def save(self):
        self.settings.set(self.script_var.get(), 'files', 'script_file')
        self.settings.set(self.map_var.get(), 'files', 'map_file')
        self.settings.set(self.ref_var.get(), 'files', 'ref_dir')
        self.settings.set(self.min_rms.get(), 'validation', 'min_rms')
        self.settings.set(self.clip_level.get(), 'validation', 'clip_level')
        self.settings.set(self.clip_percent.get(),
                          'validation', 'clip_percent')
        self.settings.set(self.cutoff_drop.get(),
                          'validation', 'cutoff_drop_ratio')
        self.settings.set(self.cutoff_win.get(),
                          'validation', 'cutoff_window_ms')
        self.settings.set(self.min_dur.get(), 'validation', 'min_duration_ms')
        self.settings.set(self.max_dur.get(), 'validation', 'max_duration_ms')
        self.settings.set(self.pref_key.get(), 'device', 'preferred_keyword')
        self.settings.set(self.avoid_key.get(), 'device', 'avoid_keyword')
        self.settings.set(self.font_size.get(), 'ui', 'font_size')
        self.settings.save()
        self.apply_callback()
        self.destroy()

# -------------------- Main Application --------------------


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Thai TTS Studio")
        self.settings = core.get_settings()
        self.root.geometry(self.settings.get('ui', 'window_size'))

        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Session", command=self.new_session)
        file_menu.add_command(label="Settings", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Ask about deleting previous session
        sessions_dir = "sessions"
        if os.path.exists(sessions_dir):
            delete_prev = messagebox.askyesno(
                "Previous Session Found",
                "Do you want to delete the previous session and start fresh?\n\n"
                "• Yes: Delete old session and create new one\n"
                "• No: Continue with existing session"
            )
            if delete_prev:
                import shutil
                try:
                    shutil.rmtree(sessions_dir)
                    print("Previous session deleted")
                except Exception as e:
                    print(f"Error deleting session: {e}")

        # Load initial data
        self.load_session_data()

        # State
        self.recording = False
        self.selected_source = tk.StringVar()
        self.font_size = tk.IntVar(value=self.settings.get('ui', 'font_size'))
        self.error_recovery = False
        self.current_line_index = None  # will be set in update_ui()

        # Worker
        self.cmd_q = queue.Queue()
        self.evt_q = queue.Queue()
        self.worker = AudioWorker(
            self.cmd_q, self.evt_q, self.session_dir, self.csv_path)
        self.worker.start()

        # Build UI
        self.build_ui()
        self.refresh_devices()
        self.update_ui()  # sets current_line_index

        # Poll events
        self.root.after(150, self.poll_events)
        self.root.bind("<space>", self.on_space)
       # self.root.after(3000, self.refresh_devices_periodic)

        self.root.focus_set()

    def on_space(self, event):
        focus = self.root.focus_get()

        if focus == self.thai_text:
            return   # allow normal typing

        self.toggle_record()
        return "break"



    def update_ui(self):
        try:
            total = len(self.lines)

            recorded_indices = {
                int(f.split("_")[1].split(".")[0]) - 1
                for f in os.listdir(self.session_dir)
                if f.startswith("line_") and f.endswith(".wav")
            }

            skipped_indices = core.get_skipped_indices(self.session_dir)
            completed = recorded_indices.union(skipped_indices)

            percent = int((len(completed) / total) * 100) if total else 0
            self.progress['value'] = percent
            self.root.title(f"Thai TTS Studio – {len(completed)}/{total}")

            next_index = None
            for i in range(total):
                if i not in completed:
                    next_index = i
                    break
            if next_index is not None:
            
                if self.current_line_index != next_index:   # ✅ ONLY update if changed
            
                    self.current_line_index = next_index
            
                    self.thai_text.delete("1.0", tk.END)
                    self.thai_text.insert("1.0", self.lines[next_index])
                    self.thai_text.tag_add("center", "1.0", "end")
            
                    self.eng_label.config(text=self.phon_map.get(str(next_index), ""))

            else:
                if self.current_line_index is not None:
            
                    self.current_line_index = None
            
                    self.thai_text.delete("1.0", tk.END)
                    self.thai_text.insert("1.0", "✓ COMPLETE")
                    self.thai_text.tag_add("center", "1.0", "end")
            
                    self.eng_label.config(text="")

        except Exception as e:
            self.error_label.config(text=f"UI Error: {str(e)}")


    def toggle_record(self):
        try:
            if self.recording:
                self.cmd_q.put({'cmd': CMD_STOP})
                return

            if self.current_line_index is None:
                messagebox.showinfo('Done', 'All recordings finished')
                return

            wav = f"line_{self.current_line_index+1:03d}.wav"
            path = os.path.join(self.session_dir, wav)

            if os.path.exists(path):
                messagebox.showwarning(
                    "Exists",
                    "This line already has audio. Use REDO if you want to overwrite."
                )
                return

            current_text = self.thai_text.get("1.0", "end-1c").strip()

            if not current_text:
                messagebox.showwarning("Empty", "Cannot record empty text")
                return

            self.cmd_q.put({
                'cmd': CMD_START,
                'wav': wav,
                'path': path,
                'line': current_text,
                'line_index': self.current_line_index
            })

        except Exception as e:
            self.error_label.config(text=f'Record error: {str(e)}')


    def load_session_data(self):
        self.lines = core.load_script()
        self.phon_map = core.load_phonetic_map()
        self.session_dir = core.get_or_create_session()
        self.csv_path = os.path.join(self.session_dir, "metadata.csv")
        core.ensure_csv_header(self.csv_path)
        self.refs = core.load_reference_list()


    def new_session(self):
        if messagebox.askyesno("New Session", "Start a new session?"):
            import shutil
            try:
                shutil.rmtree("sessions")
            except:
                pass
            self.load_session_data()
            self.update_ui()



    def build_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill='x', padx=10, pady=5)

        ttk.Label(top, text="Audio:").pack(side='left')
        self.device_combo = ttk.Combobox(top, textvariable=self.selected_source,
                                         state='readonly', width=70)
        self.device_combo.pack(side='left', padx=5)
        self.device_combo.bind('<<ComboboxSelected>>', self.on_device_selected)

        ttk.Label(top, text="Font:").pack(side='left', padx=(20, 5))
        self.font_spin = ttk.Spinbox(top, from_=16, to=150, textvariable=self.font_size,
                                     width=5, command=self.update_font)
        self.font_spin.pack(side='left')

        ttk.Button(top, text="Test", command=self.test_recording).pack(
            side='left', padx=20)

        self.progress = ttk.Progressbar(self.root, length=700)
        self.progress.pack(pady=10)

        self.thai_text = tk.Text(
            self.root,
            wrap="word",
            height=4,
            font=("Garuda", self.font_size.get()),
            relief="sunken",
            borderwidth=2,
            undo=True
        )

        self.thai_text.pack(pady=20, fill="both", expand=True)

        # center alignment
        self.thai_text.tag_configure("center", justify="center")

        self.eng_label = ttk.Label(
            self.root, font=('Arial', 14), foreground='gray')
        self.eng_label.pack()

        self.status_label = ttk.Label(self.root, font=('Arial', 14, 'bold'))
        self.status_label.pack(pady=5)

        self.warn_label = ttk.Label(
            self.root, foreground='orange', font=('Arial', 12))
        self.warn_label.pack()

        self.error_label = ttk.Label(
            self.root, foreground='red', font=('Arial', 14, 'bold'))
        self.error_label.pack()

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=20)

        self.record_btn = ttk.Button(
            btn_frame, text="● RECORD", command=self.toggle_record, width=12)
        self.record_btn.grid(row=0, column=0, padx=6)

        ttk.Button(btn_frame, text="▶ PLAY", command=self.play,
                   width=12).grid(row=0, column=1, padx=6)

        ttk.Button(btn_frame, text="↩ REDO", command=self.redo,
                   width=12).grid(row=0, column=2, padx=6)

        # DELETE button for current line
        ttk.Button(btn_frame, text="🗑 DELETE", command=self.delete_current,
                   width=12).grid(row=0, column=3, padx=6)

        ttk.Button(btn_frame, text="■ QUIT", command=self.quit,
                   width=12).grid(row=0, column=4, padx=6)

        ttk.Button(btn_frame, text="🔄 NEW", command=self.new_session,
                   width=12).grid(row=1, column=0, columnspan=5, pady=10)

        self.update_font()

    def update_font(self):
        self.thai_text.config(font=('Garuda', self.font_size.get()))
        self.settings.set(self.font_size.get(), 'ui', 'font_size')

    def refresh_devices(self):
        devices = core.get_audio_devices()
        self.device_combo['values'] = devices
        if devices:
            best = core.choose_best_device(devices)
            if best != self.selected_source.get():
                self.selected_source.set(best)
                core.set_default_device(best)

    def refresh_devices_periodic(self):
        return

    def on_device_selected(self, event=None):
        core.set_default_device(self.selected_source.get())

    def poll_events(self):
        try:
            while True:
                ev = self.evt_q.get_nowait()
                self.handle_event(ev)
                self.error_recovery = False
        except queue.Empty:
            pass
        self.update_ui()
        self.root.after(150, self.poll_events)

    def handle_event(self, ev):
        t = ev['type']
        if t == 'recording_started':
            self.recording = True
            self.record_btn.config(text='◼ STOP')
            self.status_label.config(text='🔴 RECORDING...', foreground='red')
            self.error_label.config(text='')
        elif t == 'recording_saved':
            self.recording = False
            self.record_btn.config(text='● RECORD')
            self.status_label.config(text='✓ Saved', foreground='green')
            self.warn_label.config(text='')
            self.error_label.config(text='')
            self.root.after(2000, lambda: self.status_label.config(
                text='READY', foreground='black'))
        elif t == 'recording_rejected':
            self.recording = False
            self.record_btn.config(text='● RECORD')
            self.status_label.config(text='✗ Rejected', foreground='red')
            m = ev.get('metrics', {})
            details = ev['reason']
            if m:
                details += f" (peak={m.get('peak','?')}, rms={m.get('rms','?')})"
            self.warn_label.config(text=f'⚠ {details}')
            self.error_label.config(text='')
        elif t == 'redo_complete':
            if ev.get('success', False):
                self.status_label.config(
                    text='↩ Last deleted', foreground='orange')
                self.update_ui()
            else:
                self.error_label.config(text='Nothing to redo')
            self.root.after(2000, lambda: self.status_label.config(
                text='READY', foreground='black'))
        elif t == 'line_deleted':
            if ev['success']:
                self.status_label.config(
                    text=f'Line {ev["line_index"]+1} deleted', foreground='orange')
                self.update_ui()
            else:
                self.error_label.config(text='Line not found')
            self.root.after(2000, lambda: self.status_label.config(
                text='READY', foreground='black'))
        elif t == 'error':
            error_msg = ev["err"]
            self.error_label.config(text=f'⚠ ERROR: {error_msg}')
            self.status_label.config(text='ERROR', foreground='red')
            if self.recording:
                self.recording = False
                self.record_btn.config(text='● RECORD')
            if self.error_recovery:
                while not self.cmd_q.empty():
                    try:
                        self.cmd_q.get_nowait()
                    except queue.Empty:
                        break
            self.error_recovery = True
        elif t == 'exit':
            self.root.destroy()
    
    
    
    
    
    def play(self):
        try:
            files = [
                f for f in os.listdir(self.session_dir)
                if f.startswith("line_") and f.endswith(".wav")
            ]
    
            if not files:
                self.error_label.config(text="No recordings yet.")
                return
    
            last_file = sorted(files)[-1]
            path = os.path.join(self.session_dir, last_file)
    
            # ✅ SHOW PLAYING STATUS
            self.status_label.config(text="▶ PLAYING...", foreground="blue")
            self.root.update()
    
            core.play_audio(path)
    
            # ✅ RESTORE STATUS
            self.status_label.config(text="READY", foreground="black")
    
        except Exception as e:
            self.error_label.config(text=f"Play error: {str(e)}")
    
    
    


    
    def redo(self):
        try:
            recorded = len(core.get_recorded_indices(self.csv_path))
            if recorded > 0 and messagebox.askyesno('Redo', 'Delete last recording?'):
                self.cmd_q.put({'cmd': CMD_REDO})
        except Exception as e:
            self.error_label.config(text=f'Redo error: {str(e)}')

    def delete_current(self):
        if self.current_line_index is None:
            return

        if messagebox.askyesno(
            'Skip Line',
            f'Skip line {self.current_line_index+1}?'
        ):
            # Delete wav if exists
            wav = os.path.join(
                self.session_dir,
                f"line_{self.current_line_index+1:03d}.wav"
            )
            if os.path.exists(wav):
                os.remove(wav)

            # Remove from metadata if exists
            core.delete_recording_by_line(
                self.csv_path,
                self.session_dir,
                self.current_line_index
            )

            # Mark as skipped
            core.add_skipped_index(
                self.session_dir,
                self.current_line_index
            )

            self.status_label.config(
                text=f"Line {self.current_line_index+1} skipped",
                foreground="orange"
            )

            self.update_ui()

    def test_recording(self):
        self.status_label.config(text='🔴 Testing...', foreground='orange')
        self.error_label.config(text='')
        self.root.update()

        def test_thread():
            try:
                metrics = core.test_recording(duration_sec=2)
                self.root.after(0, lambda: self.show_test_result(metrics))
            except Exception as e:
                self.root.after(0, lambda: self.error_label.config(
                    text=f'Test error: {str(e)}'))
        threading.Thread(target=test_thread, daemon=True).start()

    def show_test_result(self, metrics):
        if 'error' in metrics:
            messagebox.showerror("Test Error", metrics['error'])
            return
        accepted = metrics.get('accepted', False)
        reason = metrics.get('reason', '')
        msg = (f"Peak: {metrics['peak']}\n"
               f"RMS: {metrics['rms']}\n"
               f"Clipping: {metrics['clipping_percent']:.2f}%\n"
               f"Cut-off: {metrics['cutoff_detected']}\n"
               f"Duration: {metrics['duration_ms']:.0f}ms\n\n"
               f"Result: {'✓ ACCEPTED' if accepted else '✗ REJECTED'}\n"
               f"{reason}")
        messagebox.showinfo("Test Recording", msg)
        self.status_label.config(text='READY', foreground='black')

    def open_settings(self):
        def apply():
            self.lines = core.load_script()
            self.phon_map = core.load_phonetic_map()
            self.refs = core.load_reference_list()
            self.font_size.set(self.settings.get('ui', 'font_size'))
            self.update_font()
            self.update_ui()
        SettingsDialog(self.root, self.settings, apply)

    def quit(self):
        if messagebox.askokcancel('Quit', 'Exit?'):
            self.cmd_q.put({'cmd': CMD_EXIT})
            self.root.after(500, self.root.destroy)


def main():
    root = tk.Tk()
    app = App(root)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nClosing app (Ctrl+C)")
        try:
            app.quit()
        except:
            pass

if __name__ == '__main__':
    main()
