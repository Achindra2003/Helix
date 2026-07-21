@echo off
REM ---------------------------------------------------------------------------
REM  Helix - start locally without Docker (dev mode)
REM    Backend:  FastAPI  -> http://localhost:8000
REM    Frontend: Vite     -> http://localhost:5173  (open this one)
REM
REM  Each server opens in its own window. Close those windows to stop Helix.
REM  Provider is set in backend\.env (LLM_PROVIDER). Use stub for keyless
REM  exploring, or groq + GROQ_API_KEY for real replies.
REM ---------------------------------------------------------------------------

echo Starting Helix backend on http://localhost:8000 ...
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
    echo   ERROR: backend\.venv not found. Create it and install requirements first.
    pause
    exit /b 1
)
REM HELIX_DEV=1 lets it boot on the dev secret (P2 secure-boot check).
start "Helix backend" cmd /k "set HELIX_DEV=1 && .venv\Scripts\python.exe -m uvicorn api.main:app --port 8000 --reload"

echo Starting Helix frontend on http://localhost:5173 ...
cd /d "%~dp0frontend\app"
if not exist "node_modules" (
    echo   node_modules missing - running npm install first...
    call npm install
)
start "Helix frontend" cmd /k "npm run dev"

echo Waiting for the servers to come up ...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173

echo.
echo   Helix is starting in two windows:
echo     Frontend (open this): http://localhost:5173
echo     Backend / API docs:   http://localhost:8000/docs
echo.
echo   Close both windows to stop Helix.
