# DrishtiAI

**DrishtiAI is a full-stack prototype for AI-assisted identity-document screening.** It combines OCR, document-quality and consistency checks, suspicious-indicator analysis, optional face comparison, and a configurable risk assessment to help surface documents for further review.

> **Important:** This project is an experimental screening aid, not proof that a document or identity is genuine. Automated results can be wrong. Do not use it as the sole basis for identity, eligibility, financial, legal, or other consequential decisions. Human review and independent verification are required.

**Live demo:** Not available yet.

## What it includes

Features visible in the current codebase include:

- **OCR and field extraction** for supported document images and PDFs.
- **Document analysis** including image-quality checks, metadata/security-feature analysis, and suspicious-indicator checks.
- **Consistency and reference checks** across extracted fields and documents.
- **AI-content/provenance analysis** using the project's detector and content-credentials integrations.
- **Risk assessment and review states** to help organize screening outcomes.
- **Account and document workflows** with a FastAPI API and persistent local database.
- **Optional face comparison/capture workflow** for supported document types.

The quality of each result depends on the input file, available dependencies, and the analysis methods. These capabilities have not been independently validated for production use.

## Tech stack

| Area | Technologies |
| --- | --- |
| Frontend | React, Vite, Tailwind CSS, React Router, lucide-react |
| Backend API | Python, FastAPI, Uvicorn |
| Data | SQLite |
| OCR / documents | Tesseract, pytesseract, EasyOCR, pdf2image, PyMuPDF |
| Image / ML analysis | OpenCV, NumPy, PyTorch, torchvision |
| Additional analysis | C2PA content credentials, EXIF metadata inspection |

## Repository layout

```text
.
├── backend/
│   ├── app/                  # FastAPI app, database and analysis services
│   ├── requirements.txt      # Python dependencies
│   └── uploads/              # Runtime upload storage (not source files)
├── src/                      # React frontend
├── app.py                    # Streamlit dashboard entry point
├── package.json              # Frontend scripts and dependencies
├── vite.config.js            # Proxies /api requests to the local API
├── run_drishti.bat           # Windows launcher for both services
├── run_backend.bat           # Windows backend launcher
├── run_frontend.bat          # Windows frontend launcher
└── stop_drishti.bat          # Windows stop script
```

## Prerequisites

Install these before starting the application:

- Node.js and npm (use a version supported by the Vite version in `package.json`).
- Python 3.10 or newer.
- Tesseract OCR installed and available on your system `PATH`.
- Poppler utilities available on `PATH` for PDF-to-image conversion with `pdf2image`.
- The Python packages listed in `backend/requirements.txt`. Some ML/OCR packages are large and may take time to install.

## Run locally

Commands below are run from the repository root.

### 1. Install frontend dependencies

```bash
npm install
```

### 2. Create and activate a Python virtual environment

**Windows PowerShell**

```powershell
python -m venv backend/venv
.\backend\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

If your operating system blocks PowerShell script activation, use a terminal/session where activation is permitted or invoke the virtual environment's Python executable directly.

### 3. Configure environment variables

Copy `backend/.env.example` to `backend/.env`, then replace the placeholder session secret with a long, random, unique value before using authentication.

**Windows PowerShell**
```powershell
Copy-Item backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**macOS / Linux**
```bash
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `VERIFYSHIELD_SESSION_SECRET` in `backend/.env`. The example value is only a placeholder. Do not use the application's development fallback secret in any shared or deployed environment. SMTP settings are optional unless you need email verification or password-reset email features. The application reads these settings:

| Variable | Purpose |
| --- | --- |
| `VERIFYSHIELD_SESSION_SECRET` | Secret used to sign session and verification tokens; set a long, unique random value |
| `VERIFYSHIELD_FRONTEND_URL` | Frontend URL used by authentication flows |
| `VERIFYSHIELD_SESSION_SECURE` | Set to `true` when serving over HTTPS in a properly configured deployment |
| `VERIFYSHIELD_SMTP_HOST` | SMTP server hostname |
| `VERIFYSHIELD_SMTP_PORT` | SMTP server port |
| `VERIFYSHIELD_SMTP_USERNAME` | SMTP username |
| `VERIFYSHIELD_SMTP_PASSWORD` | SMTP password |
| `VERIFYSHIELD_SMTP_FROM_EMAIL` | Sender email address |
| `VERIFYSHIELD_SMTP_USE_TLS` | Whether SMTP TLS should be used |

Do not commit `.env` files, passwords, tokens, private documents, or other secrets. Use a separate local development secret and a strong secret for each deployed environment.

### 4. Start the application

With the Python virtual environment activated, run:

```bash
npm run dev
```

The development script starts both the FastAPI backend and Vite frontend.

- Frontend: http://localhost:5173
- Backend API: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs
- Health endpoint: http://127.0.0.1:8000/api/health

On Windows, `run_drishti.bat` is also provided to launch both services. Review the batch file before running it and ensure the prerequisites are installed.

## Useful development checks

Run these from the repository root:

```bash
npm run lint
npm run build
```

These commands are available for linting and building the frontend. A GitHub Actions workflow in `.github/workflows/frontend-checks.yml` runs both checks on pushes and pull requests targeting `main`; check the repository's **Actions** tab for the actual result. Backend tests should also be added and run before describing the project as fully tested.

## Security and privacy notes

- Use synthetic or explicitly authorized sample documents during development. Avoid uploading real identity documents or biometric data unless you have a lawful basis, informed consent, and appropriate safeguards.
- Do not expose the development server to the public internet.
- Before any deployment, review authentication, session-secret configuration, cookie settings, file-upload handling, data retention/deletion, access controls, logging, and dependency security.
- Automated document and face analysis can produce false positives and false negatives. Provide a manual-review path and do not treat a model score as a definitive authenticity determination.

## Current project status

- Full-stack project with frontend and backend source code in this repository.
- Live demo: **not available yet**.
- Automated test/build status: **not stated here; run the checks above and record verified results**.
- Production readiness: **not established**.

## License

The repository currently states **All rights reserved**. No open-source reuse license is specified.
