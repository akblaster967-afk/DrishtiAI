# DrishtiAI 🔍

**AI-powered document verification & fraud screening platform** — upload an ID/document image or PDF and get a forensic analysis: OCR field extraction, tamper/forgery detection, AI-generated content screening, face matching, and a risk verdict.

## ✨ Features

- **Document forensics** — ELA (Error Level Analysis), visual forgery analysis, security-feature checks, EXIF metadata inspection
- **OCR + field extraction** — Tesseract-based OCR with hallucination/broken-glyph forensics; universal & document-specific field extractors (e.g., Aadhaar)
- **AI-generated content screening** — deep-learning detector (PyTorch) + C2PA content-credentials provenance checks
- **Identity & consistency** — face matching, cross-document consistency, reference comparison
- **Risk engine** — combines all indicators into a screening verdict with audit logs

## 🧱 Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS 4, React Router, lucide-react |
| Backend | FastAPI, Uvicorn, SQLite |
| ML / Vision | PyTorch, OpenCV, Tesseract (pytesseract/EasyOCR), pdf2image, PyMuPDF |

## 📂 Project Structure

```
├── backend/
│   ├── app/              # FastAPI app, routes, services (forensics, OCR, ML)
│   ├── requirements.txt
│   └── uploads/          # runtime upload storage (gitignored)
├── src/                  # React frontend (pages, components)
├── app.py                # optional Streamlit dashboard
├── vite.config.js        # proxies /api -> http://127.0.0.1:8000
├── run_drishti.bat       # one-click launcher - backend + frontend (Windows)
├── run_backend.bat       # backend-only launcher (Windows)
├── run_frontend.bat      # frontend-only launcher (Windows)
└── stop_drishti.bat      # stop both servers (Windows)
```

## 🚀 Getting Started

### Prerequisites
- Node.js (with npm)
- Python 3.10+
- Tesseract OCR installed and on PATH

### Setup

```bash
# 1. Frontend dependencies
npm install

# 2. Backend dependencies
pip install -r backend/requirements.txt

# 3. Create backend/.env with your app secrets (SMTP credentials, etc.)
```

### Run (backend + frontend together)

```bash
npm run dev
```

or on Windows, simply double-click **`run_drishti.bat`** (auto-installs missing dependencies, then starts both servers).

### One-click command files (Windows)

| File | What it does |
|---|---|
| `run_drishti.bat` | Starts **both** backend + frontend together |
| `run_backend.bat` | Starts **only** the FastAPI backend (with auto-reload) → http://127.0.0.1:8000 |
| `run_frontend.bat` | Starts **only** the Vite frontend → http://localhost:5173 |
| `stop_drishti.bat` | Stops both servers (frees ports 8000 / 5173) |

All launchers auto-install missing dependencies (`npm install` / `pip install -r backend/requirements.txt`) on first run.

- Frontend → http://localhost:5173
- Backend API → http://127.0.0.1:8000 (Swagger docs at `/docs`)

## 📄 License

All rights reserved.
