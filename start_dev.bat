@echo off
echo Starting PaperBot engine (background)...
start "PaperBot Engine" cmd /k "cd backend && py -m uvicorn api:app --reload --port 8000"
timeout /t 3 >nul
echo Starting React UI...
start "PaperBot UI" cmd /k "cd paperbot && npm start"
echo.
echo Engine: http://localhost:8000/api/state
echo UI:     http://localhost:3000
