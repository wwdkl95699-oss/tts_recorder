# Thai TTS Studio

Lightweight desktop tool for fast creation of Thai TTS datasets.

Thai TTS Studio is a simple Tkinter-based recording app designed for efficient, line-by-line dataset creation.
It provides a clean workflow with automatic validation, session tracking, playback tools, and keyboard shortcuts for fast recording sessions.

---

## ✨ Features

• Line-by-line recording workflow
• Automatic audio validation (RMS, clipping, duration, cutoff detection)
• Session tracking with resume support
• Playback, redo, delete, and skip tools
• Keyboard-driven workflow (Space = record/stop)
• Device selection with live testing
• Lightweight (pure Python + Tkinter)

---

## 📸 Workflow

1. Load script
2. Record line-by-line
3. Auto-validation checks audio quality
4. Playback / redo if needed
5. Export clean dataset

---

## 🚀 Installation

### Requirements

• Python 3.9+
• Linux / macOS (Windows likely works too)

### Install

```bash
git clone https://github.com/YOURNAME/thai-tts-studio.git
cd thai-tts-studio

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## ▶️ Run

```bash
python gui7.py
```

---

## 🎹 Controls

| Key / Button | Action                |
| ------------ | --------------------- |
| Spacebar     | Record / Stop         |
| PLAY         | Play last recording   |
| REDO         | Delete last recording |
| DELETE       | Skip current line     |
| NEW          | Start new session     |

---

## 📁 Project Structure

```
thai-tts-studio/
│
├── gui7.py          # Main UI
├── core/            # Audio + dataset logic
├── sessions/        # Recording sessions
└── README.md
```

---

## ⚙️ Settings

Settings panel includes:

• Script file
• Phonetic map
• Reference directory
• Validation thresholds
• Audio device preferences
• UI font size

---

## 🎯 Design Goals

Thai TTS Studio focuses on:

• Speed
• Simplicity
• Reliability
• Clean datasets

No heavy frameworks, no complexity — just fast recording.

---

## 🧪 Status

Stable for daily dataset recording use.
Still evolving — suggestions welcome.

---

## 🤝 Contributing

Pull requests and ideas welcome.
Open an issue if something breaks.

---

## 📜 License

MIT License
