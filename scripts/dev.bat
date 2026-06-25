@echo off
setlocal

set "ROOT=%~dp0.."

if not exist "%ROOT%\.env" (
    echo Missing .env file. Copying from deploy\.env.example...
    copy "%ROOT%\deploy\.env.example" "%ROOT%\.env"
    echo Created .env from template. Edit it with your settings.
)

echo === Starting Yandex Mediaplan Dev ===

pushd "%ROOT%" || exit /b 1

echo --- Starting backend services (API + Redis)...
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up --build -d

echo --- Starting frontend dev server...
pushd "%ROOT%\frontend" || exit /b 1
if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)
echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
call npm run dev
popd

popd
exit /b %ERRORLEVEL%
