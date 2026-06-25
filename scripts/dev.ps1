param(
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Missing .env file. Copying from deploy/.env.example..."
    Copy-Item (Join-Path $Root "deploy/.env.example") $EnvFile
    Write-Host "Created .env from template. Edit it with your settings."
}

Write-Host "=== Starting Yandex Mediaplan Dev ==="

Push-Location $Root
try {
    Write-Host "--- Starting backend services (API + Redis)..."
    docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up --build -d

    if (-not $BackendOnly) {
        Write-Host "--- Starting frontend dev server..."
        Push-Location (Join-Path $Root "frontend")
        try {
            if (-not (Test-Path "node_modules")) {
                Write-Host "Installing frontend dependencies..."
                npm install
            }
            Write-Host ""
            Write-Host "Backend: http://localhost:8000"
            Write-Host "Frontend: http://localhost:5173"
            Write-Host ""
            npm run dev
        } finally {
            Pop-Location
        }
    } else {
        Write-Host ""
        Write-Host "Backend: http://localhost:8000"
        Write-Host "Run 'cd frontend && npm run dev' separately for frontend."
        Write-Host ""
        docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml logs -f
    }
} finally {
    Pop-Location
}
