#!/usr/bin/env python3
# core.py - modular core for Thai TTS Studio

import os
import json
import csv
import wave
import sounddevice as sd
import audioop
import numpy as np
import scipy.io.wavfile as wavfile
import simpleaudio as sa
import threading
import time
from datetime import datetime

# ---------- Configuration ----------DJIRecorder
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "files": {
        "script_file": "script.txt",
        "map_file": "phonetic_map.json",
        "ref_dir": "references"
    },
    "validation": {
      "min_rms": 0.04,
      "clip_level": 30000,
      "clip_percent": 0.2,
      "cutoff_drop_ratio": 0.2,
      "cutoff_window_ms": 200,
      "min_duration_ms": 600,
      "max_duration_ms": 30000
    },
    "device": {
        "preferred_keyword": "USB",
        "avoid_keyword": "HDMI"
    },
    "ui": {
        "font_size": 32,
        "window_size": "900x700"
    }
}



import sounddevice as sd

# ---------- Audio Device Handling ----------
def get_audio_devices():
    devices = []
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0:
            devices.append(f"{i}: {dev['name']}")
    return devices
class Settings:
    def __init__(self):
        self.config = self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return DEFAULT_CONFIG.copy()

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)

    def get(self, section, key=None):
        if key is None:
            return self.config.get(section, {})
        return self.config.get(section, {}).get(key)

    def set(self, value, section, key):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value

_settings = None
def get_settings():
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

# ---------- File Loading ----------
def load_script():
    """Load Thai script lines from file."""
    settings = get_settings()
    script_file = settings.get('files', 'script_file')
    if not os.path.exists(script_file):
        return ["สวัสดี", "ขอบคุณ", "ใช่", "ไม่"]
    with open(script_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def load_phonetic_map():
    """Load phonetic mapping (line index -> phonetic)."""
    settings = get_settings()
    map_file = settings.get('files', 'map_file')
    if os.path.exists(map_file):
        with open(map_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_reference_list():
    """Return list of reference audio paths for all lines (or None)."""
    settings = get_settings()
    ref_dir = settings.get('files', 'ref_dir')
    lines = load_script()
    refs = []
    for i, _ in enumerate(lines):
        path = os.path.join(ref_dir, f"ref_{i+1:03d}.wav")
        refs.append(path if os.path.exists(path) else None)
    return refs



def choose_best_device(devices):
    settings = get_settings()
    preferred = settings.get('device', 'preferred_keyword')
    avoid = settings.get('device', 'avoid_keyword')
    best = devices[0] if devices else ""
    for d in devices:
        if preferred.lower() in d.lower():
            best = d
            break
    for d in devices:
        if avoid.lower() not in d.lower():
            best = d
            break
    return best

def set_default_device(device_string):
    try:
        idx = int(device_string.split(':')[0])
        settings = get_settings()
        settings.set(idx, 'device', 'selected_index')
        settings.save()
    except:
        pass

def get_selected_device_index():
    settings = get_settings()
    return settings.get('device', 'selected_index')

# ---------- Audio Playback ----------
def play_audio(path: str):
    """
    Safe playback using external tools to avoid PortAudio/PyAudio segfaults.
    Tries: ffplay -> paplay -> aplay
    """
    import os
    import shutil
    import subprocess

    if not path or not os.path.exists(path):
        raise FileNotFoundError(path)

    # Prefer ffplay (most reliable for wav)
    if shutil.which("ffplay"):
        # -nodisp (no window), -autoexit (quit when done), -loglevel error (quiet)
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    # PipeWire/Pulse fallback
    if shutil.which("paplay"):
        subprocess.Popen(
            ["paplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    # ALSA fallback (wav only)
    if shutil.which("aplay"):
        subprocess.Popen(
            ["aplay", "-q", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    raise RuntimeError("No audio player found: install ffmpeg (ffplay) or pulseaudio-utils (paplay) or alsa-utils (aplay)")
    
    

import sounddevice as sd
import soundfile as sf
import numpy as np
import threading


class DJIRecorder:
    def __init__(self):
        self.frames = []
        self.stream = None
        self.recording = False
        self.filename = None
        self.actual_rate = None
        self.channels = 1
        self.blocksize = 1024

    def _pick_default_input_device(self):
        devices = sd.query_devices()
    
        # 1️⃣ If user selected device in settings
        dev_index = get_selected_device_index()
        if dev_index is not None:
            try:
                dev = devices[int(dev_index)]
                if dev['max_input_channels'] > 0:
                    return int(dev_index)
            except Exception:
                pass
    
        # 2️⃣ Prefer PulseAudio
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0 and "pulse" in dev['name'].lower():
                return i
    
        # 3️⃣ System default
        default = sd.default.device[0]
        if default is not None:
            return default
    
        # 4️⃣ First available input
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                return i
    
        return None
    
    def start(self, filename):
        self.filename = filename
        self.frames = []
        self.recording = True

        device_index = self._pick_default_input_device()
        if device_index is None:
            raise RuntimeError("No input audio device found.")

        candidate_rates = [48000, 44100]

        last_err = None
        for rate in candidate_rates:
            try:
                self.actual_rate = rate

                def callback(indata, frames, time, status):
                    if status:
                        print(status)
                    if self.recording:
                        self.frames.append(indata.copy())

                self.stream = sd.InputStream(
                    device=device_index,
                    samplerate=rate,
                    channels=self.channels,
                    callback=callback,
                    blocksize=self.blocksize,
                )

                self.stream.start()
                return

            except Exception as e:
                last_err = e
                self.stream = None

        raise RuntimeError(
            f"Failed to open device {device_index} at rates {candidate_rates}. "
            f"Last error: {last_err}"
        )

    def stop(self):
        self.recording = False
    
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
    
        # ✅ if nothing captured, return None
        if not self.frames:
            return None
    
        audio = np.concatenate(self.frames, axis=0)
    
        # if stereo/2D, flatten or keep mono
        if audio.ndim > 1:
            audio = audio[:, 0]
    
        # write float directly (cleanest)
        sf.write(self.filename, audio.astype(np.float32), self.actual_rate, subtype='PCM_16')
        return self.filename
        
        
# ---------- Validation ----------
import soundfile as sf
import numpy as np
import os

class AudioValidator:
    def __init__(self):
        self.settings = get_settings()
        self.val = self.settings.get('validation')

    def analyze(self, wav_path):
        if not wav_path:
            raise FileNotFoundError("No wav path provided")
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"File not found: {wav_path}")
        if os.path.getsize(wav_path) < 44:  # smaller than WAV header
            raise ValueError(f"WAV file too small/empty: {wav_path}")

        # ✅ Read with soundfile (matches sf.write)
        data, rate = sf.read(wav_path, always_2d=False)

        # mix to mono
        if isinstance(data, np.ndarray) and data.ndim > 1:
            data = data.mean(axis=1)

        data = data.astype(np.float32)

        # ✅ Ensure float is in [-1,1]
        # soundfile usually gives float already; if not, normalize
        if data.size and np.max(np.abs(data)) > 1.5:
            data = data / 32768.0

        duration_ms = (len(data) / rate) * 1000.0

        rms = float(np.sqrt(np.mean(data**2))) if len(data) else 0.0
        peak = float(np.max(np.abs(data))) if len(data) else 0.0

        # Convert your clip_level (int16 like 30000) into float threshold
        clip_level_float = float(self.val['clip_level']) / 32768.0
        clipping = (np.sum(np.abs(data) > clip_level_float) / len(data) * 100.0) if len(data) else 0.0

        cutoff_detected = self._detect_cutoff(data, rate)

        return {
            'duration_ms': duration_ms,
            'rms': rms,                 # now 0..1 scale
            'peak': peak,               # now 0..1 scale
            'peak_int16': peak * 32767, # optional for display
            'clipping_percent': clipping,
            'cutoff_detected': cutoff_detected
        }

    def _detect_cutoff(self, data, rate):
        window_ms = self.val['cutoff_window_ms']
        window_samples = int(rate * window_ms / 1000)
        if len(data) < window_samples * 2:
            return False
        first = data[:window_samples]
        last = data[-window_samples:]
        rms_first = np.sqrt(np.mean(first**2))
        rms_last = np.sqrt(np.mean(last**2))
        if rms_first == 0:
            return False
        ratio = rms_last / rms_first
        return ratio < self.val['cutoff_drop_ratio']

    def is_acceptable(self, metrics):
        v = self.val

        if metrics['duration_ms'] < v['min_duration_ms']:
            return False, "Too short"
        if metrics['duration_ms'] > v['max_duration_ms']:
            return False, "Too long"

        # ✅ min_rms is now on 0..1 scale
        if metrics['rms'] < v['min_rms']:
            return False, "Too quiet"

        if metrics['clipping_percent'] > v['clip_percent']:
            return False, "Clipping"

        if metrics['cutoff_detected']:
            return False, "Cut off"

        return True, "OK"

    def _detect_cutoff(self, data, rate):
        window_ms = self.val['cutoff_window_ms']
        window_samples = int(rate * window_ms / 1000)
        if len(data) < window_samples * 2:
            return False
        first = data[:window_samples]
        last = data[-window_samples:]
        rms_first = np.sqrt(np.mean(first**2))
        rms_last = np.sqrt(np.mean(last**2))
        if rms_first == 0:
            return False
        ratio = rms_last / rms_first
        return ratio < self.val['cutoff_drop_ratio']

    def is_acceptable(self, metrics):
        v = self.val
        if metrics['duration_ms'] < v['min_duration_ms']:
            return False, "Too short"
        if metrics['duration_ms'] > v['max_duration_ms']:
            return False, "Too long"
        if metrics['rms'] < v['min_rms']:
            return False, "Too quiet"
        if metrics['clipping_percent'] > v['clip_percent']:
            return False, "Clipping"
        if metrics['cutoff_detected']:
            return False, "Cut off"
        return True, "OK"

# ---------- Session Management ----------
def create_session():
    """Create a new session folder with timestamp."""
    sessions_root = "sessions"
    os.makedirs(sessions_root, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join(sessions_root, f"session_{timestamp}")
    os.makedirs(session_dir)
    return session_dir

def ensure_csv_header(csv_path):
    """Create CSV with header if it doesn't exist."""
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "audio_file", "text", "line_index",
                "duration_ms", "rms", "peak", "clipping", "cutoff"
            ])

def get_recorded_indices(csv_path):
    """Return set of line indices that have been recorded."""
    indices = set()
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    indices.add(int(row['line_index']))
                except (ValueError, KeyError):
                    continue
    return indices

def append_recording(csv_path, wav_file, text, line_index, metrics):
    """Append a new recording to metadata.csv, including line index."""
    ensure_csv_header(csv_path)
    with open(csv_path, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            wav_file, text, line_index,
            metrics['duration_ms'], metrics['rms'], metrics['peak'],
            metrics['clipping_percent'], metrics['cutoff_detected']
        ])

def delete_recording_by_line(csv_path, session_dir, line_index):
    """
    Remove CSV row and delete audio file for a given line index.
    Returns True if found and deleted, False otherwise.
    """
    if not os.path.exists(csv_path):
        return False
    rows = []
    found = False
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if int(row['line_index']) == line_index:
                audio_path = os.path.join(session_dir, row['audio_file'])
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                found = True
            else:
                rows.append(row)
    if found:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return found

def remove_last_recording(csv_path, session_dir, idx=None):
    """Remove the most recent recording (by last CSV row)."""
    if not os.path.exists(csv_path):
        return False
    with open(csv_path, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return False
    last = rows[-1]
    line_index = int(last['line_index'])
    return delete_recording_by_line(csv_path, session_dir, line_index)

# ---------- Test Recording ----------
def test_recording(duration_sec=2):
    """Record a short test and return metrics."""
    temp = "test_temp.wav"
    rec = DJIRecorder()
    rec.start(temp)
    time.sleep(duration_sec)
    rec.stop()
    val = AudioValidator()
    try:
        metrics = val.analyze(temp)
        ok, reason = val.is_acceptable(metrics)
        metrics['accepted'] = ok
        metrics['reason'] = reason
    except Exception as e:
        metrics = {'error': str(e)}
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    return metrics
    
def get_skipped_indices(session_dir):
    path = os.path.join(session_dir, "skipped.txt")
    if not os.path.exists(path):
        return set()
    with open(path, "r") as f:
        return set(int(x.strip()) for x in f if x.strip().isdigit())


def add_skipped_index(session_dir, line_index):
    path = os.path.join(session_dir, "skipped.txt")
    with open(path, "a") as f:
        f.write(f"{line_index}\n")

def get_or_create_session():
    import os
    sessions_dir = "sessions"
    os.makedirs(sessions_dir, exist_ok=True)

    existing = sorted(
        d for d in os.listdir(sessions_dir)
        if os.path.isdir(os.path.join(sessions_dir, d))
    )

    if existing:
        latest = os.path.join(sessions_dir, existing[-1])
        print(f"Resuming session: {latest}")
        return latest

    return create_session()




# core.py (append at the end)

def get_metadata_text(csv_path, line_index):
    """Return the text for a given line from metadata, or None if not found."""
    if not os.path.exists(csv_path):
        return None
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row['index']) == line_index:
                return row['text']
    return None

def update_metadata_text(csv_path, line_index, new_text):
    """Update the text field of an existing metadata row. Returns True if updated."""
    if not os.path.exists(csv_path):
        return False
    rows = []
    updated = False
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if int(row['index']) == line_index:
                row['text'] = new_text
                updated = True
            rows.append(row)
    if updated:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return updated
    
    

