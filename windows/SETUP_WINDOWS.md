# JARVIS-MKIII — Windows Installation Guide

**Tested on:** Windows 10 22H2 / Windows 11 23H2
**Python:** 3.12 · **Node:** 20 LTS · **CUDA:** 12.x (optional)

---

## 1. Prerequisites

Install all four tools before proceeding. Each installer requires Administrator rights.

### Python 3.12
1. Download from **https://www.python.org/downloads/windows/**
   Choose the **Windows installer (64-bit)** for Python 3.12.x
2. Run the installer
3. **Check "Add python.exe to PATH"** on the first screen — critical
4. Click **Install Now**
5. Verify: open a new terminal and run `python --version`

### Git
1. Download from **https://git-scm.com/download/win**
2. Run installer with all defaults
3. Verify: `git --version`

### Node.js 20 LTS
1. Download from **https://nodejs.org/en/download** — choose **LTS (20.x), Windows 64-bit**
2. Run installer with all defaults (includes npm)
3. Verify: `node --version` and `npm --version`

### CUDA 12.x Toolkit *(optional — enables GPU-accelerated Whisper)*
> Skip this if you don't have an NVIDIA GPU. JARVIS falls back to CPU automatically.

1. Check your GPU supports CUDA: **https://developer.nvidia.com/cuda-gpus**
2. Download **CUDA Toolkit 12.x** from **https://developer.nvidia.com/cuda-downloads**
   Select: Windows → x86_64 → your Windows version → exe (local)
3. Run the installer, choose **Express** installation
4. Verify: `nvcc --version`

---

## 2. Clone and Set Up

Open **Command Prompt** or **PowerShell** (not as Administrator).

```bat
git clone https://github.com/AGENT17-tech/JARVIS-MKIII.git
cd JARVIS-MKIII
```

### Create and activate the virtual environment
```bat
python -m venv venv
venv\Scripts\activate
```
Your prompt should now show `(venv)`.

### Install Python dependencies
```bat
pip install --upgrade pip
pip install -r windows\requirements_windows.txt
```

> **If you have a CUDA GPU**, install the GPU-enabled PyTorch build after the above:
> ```bat
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
> ```

### Install HUD dependencies
```bat
cd hud
npm install
cd ..
```

---

## 3. Vault Setup — Storing API Keys

JARVIS stores secrets in an AES-256 encrypted vault. You need to initialise it once and store your API keys.

### Step 1 — Initialise the vault
```bat
venv\Scripts\activate
cd backend
set JARVIS_VAULT_PASSWORD=your-password-here
python core\vault.py init
```
When prompted, enter and confirm your master password.

### Step 2 — Store your API keys
Run one command per key. Each will prompt you to paste the value:
```bat
python core\vault.py set GROQ_API_KEY
python core\vault.py set ANTHROPIC_API_KEY
python core\vault.py set TELEGRAM_BOT_TOKEN
python core\vault.py set TELEGRAM_CHAT_ID
```

### Step 3 — Verify keys were stored
```bat
python core\vault.py list
```

### Setting the vault password for service startup
The bat launcher needs the password at runtime so services can unlock the vault without prompting. Two options:

**Option A — Environment variable (simplest):**
Edit `windows\start_jarvis.bat` and replace the placeholder:
```bat
set JARVIS_VAULT_PASSWORD=your-password-here
```

**Option B — Password file (more secure):**
Create `%USERPROFILE%\JARVIS_MKIII\.vault_pass` containing only the password on one line.
The vault auto-detects this file. Remove the `set JARVIS_VAULT_PASSWORD=` line from the bat file.

> **Security note:** If using Option A, do not commit `start_jarvis.bat` to a public repository with a real password in it.

---

## 4. Configuration

### Location: `backend\config\settings.py`

Open the file and review these values for Windows:

```python
LAT  = 30.0444   # Your latitude  — used for weather
LON  = 31.2357   # Your longitude
CITY = "Cairo"   # Your city name

class ModelConfig(BaseModel):
    groq_model      = "llama-3.3-70b-versatile"  # Groq cloud model
    local_model     = "llava:7b"                  # Ollama vision model
    ollama_host     = "http://localhost:11434"    # Ollama server address

class ServerConfig(BaseModel):
    host  = "0.0.0.0"   # Keep as-is for LAN access
    port  = 8000         # Change if 8000 is taken
```

**Update your coordinates and city name** for accurate weather and briefings.

### Ollama (local vision model) — optional
If you want LLaVA vision support, install Ollama for Windows from **https://ollama.com/download/windows**, then pull the model:
```bat
ollama pull llava:7b
```
JARVIS works without Ollama — vision features will report unavailable.

---

## 5. Launch

From the repo root:
```bat
windows\start_jarvis.bat
```

This opens three command windows:
- **JARVIS Backend** — FastAPI on `http://localhost:8000`
- **JARVIS Voice** — STT + TTS pipeline
- **JARVIS HUD** — Electron interface

Wait about 15–20 seconds for the voice pipeline to load Kokoro and Whisper.

### To stop JARVIS
```bat
windows\stop_jarvis.bat
```

### API dashboard
Once running, open **http://localhost:8000/docs** in a browser to see all available endpoints.

---

## 6. Troubleshooting

### CUDA / GPU not found
```
[STT] CUDA failed (...), falling back to CPU...
```
This is expected if CUDA is not installed or your GPU is not CUDA-capable. CPU inference works — it is slower (5–10 s per transcription instead of <1 s). No action needed.

If you have a CUDA GPU and want to enable it:
1. Verify CUDA is installed: `nvcc --version`
2. Reinstall PyTorch with CUDA support:
   ```bat
   pip install torch --index-url https://download.pytorch.org/whl/cu121
   ```

---

### Microphone not detected / no STT response
`sounddevice` uses Windows audio APIs — it requires microphone access to be granted.

1. Open **Settings → Privacy & Security → Microphone**
2. Enable **"Microphone access"**
3. Enable **"Let desktop apps access your microphone"**
4. Restart JARVIS

To list available audio devices and find your mic index:
```bat
venv\Scripts\python.exe -c "import sounddevice; print(sounddevice.query_devices())"
```

---

### Port 8000 already in use
```
[ERROR] address already in use — port 8000
```
Find and kill the blocking process:
```bat
netstat -ano | findstr :8000
```
This prints a line like `TCP  0.0.0.0:8000  ...  LISTENING  12345`. The last number is the PID.
```bat
taskkill /PID 12345 /F
```
Then relaunch JARVIS. Alternatively, change the port in `backend\config\settings.py` → `ServerConfig.port` and update `windows\start_jarvis.bat` accordingly.

---

### pycaw / volume control error
```
Windows mic mute failed: No module named 'pycaw'
```
```bat
pip install pycaw comtypes
```

---

### pywin32 / window focus error
```
ImportError: No module named 'win32gui'
```
```bat
pip install pywin32
python venv\Scripts\pywin32_postinstall.py -install
```
The post-install step is required for `win32gui` to register correctly.

---

### screen-brightness-control error
```
Windows brightness control failed: ...
```
```bat
pip install screen-brightness-control
```
Note: brightness control requires a laptop display or a monitor that supports DDC/CI. External monitors connected via DisplayPort/HDMI may not respond.

---

### `venv\Scripts\activate` is not recognised
If PowerShell blocks script execution:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then retry `venv\Scripts\activate`.

---

### Kokoro TTS has no audio output
1. Check Windows default audio output: **Settings → System → Sound → Output**
2. If using Bluetooth headphones, ensure they are connected before starting JARVIS
3. Test audio manually:
   ```bat
   venv\Scripts\python.exe -c "import sounddevice; import numpy as np; sounddevice.play(np.zeros(4800, dtype='float32'), 48000); sounddevice.wait()"
   ```
   No error = audio system is working. Silence = wrong output device.

---

## Quick Reference

| Task | Command |
|------|---------|
| Activate venv | `venv\Scripts\activate` |
| Start JARVIS | `windows\start_jarvis.bat` |
| Stop JARVIS | `windows\stop_jarvis.bat` |
| Add a secret | `cd backend && python core\vault.py set KEY_NAME` |
| List secrets | `cd backend && python core\vault.py list` |
| API docs | http://localhost:8000/docs |
| Update deps | `pip install -r windows\requirements_windows.txt --upgrade` |
