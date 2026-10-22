@echo off
setlocal
cd /d "%~dp0"

REM Runs the whole project locally: Postgres + LiveKit (Docker), migrations/seed,
REM then Chroma, API, agent worker, scheduler and frontend each in their own window,
REM plus a Cloudflare quick tunnel to the frontend.
REM Prereqs: Docker Desktop, uv, pnpm; .env and frontend\.env.local filled in.
REM Optional: cloudflared (winget install Cloudflare.cloudflared).
REM
REM Switches (set in .env or the shell; the shell wins):
REM   TELEPHONY=1   real phone calls: LiveKit + Redis + livekit-sip from
REM                 docker-compose.telephony.yml (see docs/telephony-setup.md)
REM   SKIP_TUNNEL=1 don't start the Cloudflare tunnel
REM   CLOUDFLARE_TUNNEL_TOKEN=...  run a named tunnel instead of a quick one

if not exist ".env" (
    echo [ERROR] .env not found. Copy .env.example to .env and fill it in.
    exit /b 1
)
if not exist "frontend\.env.local" (
    echo [ERROR] frontend\.env.local not found. Copy frontend\.env.example and fill it in.
    exit /b 1
)

REM Read the switches above from .env unless already set in the shell.
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="TELEPHONY" if not defined TELEPHONY set "TELEPHONY=%%B"
    if /i "%%A"=="SKIP_TUNNEL" if not defined SKIP_TUNNEL set "SKIP_TUNNEL=%%B"
    if /i "%%A"=="CLOUDFLARE_TUNNEL_TOKEN" if not defined CLOUDFLARE_TUNNEL_TOKEN set "CLOUDFLARE_TUNNEL_TOKEN=%%B"
    if /i "%%A"=="JWT_SECRET" set "ENV_JWT_SECRET=%%B"
)
set "FRONTEND_FASTAPI_URL="
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("frontend\.env.local") do (
    if /i "%%A"=="NEXT_PUBLIC_FASTAPI_URL" set "FRONTEND_FASTAPI_URL=%%B"
)

REM Re-point LIVEKIT_URL at this machine's current LAN IP (DHCP may have changed it).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\set-livekit-lan-ip.ps1" -EnvFile "%~dp0frontend\.env.local"
REM LiveKit advertises its node IP to browsers as the media address. It must be the
REM current LAN IP, so the container is recreated with --node-ip on every run.
set "LIVEKIT_NODE_IP="
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\set-livekit-lan-ip.ps1" -PrintIp') do set "LIVEKIT_NODE_IP=%%I"
if not defined LIVEKIT_NODE_IP set "LIVEKIT_NODE_IP=127.0.0.1"
echo LiveKit node IP: %LIVEKIT_NODE_IP%

echo === Starting Postgres ===
docker start telco-pg >nul 2>&1 || docker run -d --name telco-pg -e POSTGRES_USER=telco -e POSTGRES_PASSWORD=telco -e POSTGRES_DB=telco -p 5435:5432 postgres:16-alpine
if errorlevel 1 ( echo [ERROR] Could not start Postgres container. & exit /b 1 )

REM LiveKit (7880) is shared with the RealEstateAgent project: each agent worker
REM only joins rooms dispatched to its own AGENT_NAME. A server that is already
REM up is reused untouched, since recreating it would drop the other project's calls.
REM Both LiveKit setups bind port 7880, so only one may run at a time.
if "%TELEPHONY%"=="1" (
    docker ps --filter "name=livekit-sip" --format "{{.Names}}" | findstr . >nul
    if not errorlevel 1 (
        echo === Telephony LiveKit already running, reusing it ===
    ) else (
        echo === Starting LiveKit + Redis + livekit-sip ^(TELEPHONY=1^) ===
        docker stop livekit >nul 2>&1
        docker compose -f docker-compose.telephony.yml up -d
        if errorlevel 1 ( echo [ERROR] Could not start the telephony stack. Is the RealEstateAgent telephony stack holding its ports? & exit /b 1 )
    )
) else (
    curl -s -o nul http://localhost:7880 >nul 2>&1
    if not errorlevel 1 (
        echo === LiveKit already running on 7880, reusing it ===
    ) else (
        echo === Starting LiveKit ===
        docker rm -f livekit >nul 2>&1
        docker run -d --name livekit -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server:latest --dev --bind 0.0.0.0 --node-ip %LIVEKIT_NODE_IP%
        if errorlevel 1 ( echo [ERROR] Could not start LiveKit container. & exit /b 1 )
    )
)

echo === Waiting for Postgres ===
:waitpg
docker exec telco-pg pg_isready -U telco >nul 2>&1
if errorlevel 1 ( timeout /t 2 /nobreak >nul & goto waitpg )

echo === Backend: install deps, migrate, seed ===
pushd backend
call uv sync
if errorlevel 1 ( popd & exit /b 1 )
call uv run alembic upgrade head
if errorlevel 1 ( popd & exit /b 1 )
call uv run python -m app.data.seed_all
popd

REM Knowledge-base vector store: the Chroma server from the backend's own uv env
REM (same version as the client), data in backend\storage\chroma. It runs as a
REM server, not embedded, because the API, agent worker and scheduler all share
REM it. The backend reaches it at CHROMA_HOST/CHROMA_PORT (localhost:8002, set in .env).
curl -sf http://localhost:8002/api/v2/heartbeat >nul 2>&1
if errorlevel 1 (
    echo === Starting Chroma ===
    start "Chroma (8002)" /d "%~dp0backend" cmd /k uv run chroma run --path storage\chroma --port 8002
)

echo === Waiting for Chroma ===
set /a CHROMA_TRIES=0
:waitchroma
curl -sf http://localhost:8002/api/v2/heartbeat >nul 2>&1
if not errorlevel 1 goto chromaup
set /a CHROMA_TRIES+=1
if %CHROMA_TRIES% geq 30 ( echo [WARN] Chroma isn't answering on port 8002; the knowledge base won't work until it does. & goto chromaup )
timeout /t 2 /nobreak >nul
goto waitchroma
:chromaup

echo === Frontend: install deps ===
pushd frontend
if not exist node_modules call pnpm install
popd

echo === Launching services ===
start "API (8011)"     /d "%~dp0backend"  cmd /k uv run uvicorn app.main:app --reload --port 8011
start "Agent worker"   /d "%~dp0backend"  cmd /k uv run python -m app.agent.worker start
start "Scheduler"      /d "%~dp0backend"  cmd /k uv run python -m app.scheduler.worker
start "Frontend (3001)" /d "%~dp0frontend" cmd /k pnpm dev

set "TUNNEL_STARTED="
if not "%SKIP_TUNNEL%"=="1" (
    where cloudflared >nul 2>&1
    if errorlevel 1 (
        echo [WARN] cloudflared not found, skipping the tunnel. Install: winget install Cloudflare.cloudflared
    ) else (
        set "TUNNEL_STARTED=1"
        if defined CLOUDFLARE_TUNNEL_TOKEN (
            start "Tunnel" cmd /k cloudflared tunnel run --token %CLOUDFLARE_TUNNEL_TOKEN%
        ) else (
            start "Tunnel" cmd /k cloudflared tunnel --url http://localhost:3001
        )
    )
)

echo.
echo Customer widget: http://localhost:3001
echo Admin dashboard: http://localhost:3001/login
if defined TUNNEL_STARTED (
    echo Public dashboard: see the https://....trycloudflare.com URL in the "Tunnel" window
    echo   ^(dashboard + scheduling only; voice/chat work on this machine, not through the tunnel^)
    if defined FRONTEND_FASTAPI_URL echo [WARN] frontend\.env.local sets NEXT_PUBLIC_FASTAPI_URL, so the dashboard won't load through the tunnel. Clear it to use the /backend proxy.
    if "%ENV_JWT_SECRET%"=="" echo [WARN] JWT_SECRET is empty but the dashboard is public. Set a long random value in .env.
    if "%ENV_JWT_SECRET%"=="change-this-to-a-long-random-string" echo [WARN] JWT_SECRET is the default but the dashboard is public. Set a long random value in .env.
    if "%ENV_JWT_SECRET%"=="dev-secret-change-me" echo [WARN] JWT_SECRET is the default but the dashboard is public. Set a long random value in .env.
)
if "%TELEPHONY%"=="1" (
    echo Phone calls: schedule a call with a "Dial phone number" in the dashboard.
    echo Stop: close the service windows, then "docker stop telco-pg". LiveKit is shared: stop it with "docker compose -f docker-compose.telephony.yml stop" only if RealEstateAgent isn't using it.
) else (
    echo Close the service windows to stop them; run "docker stop telco-pg" to stop Postgres. LiveKit is shared: "docker stop livekit" only if RealEstateAgent isn't using it.
)
endlocal
