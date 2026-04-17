$ErrorActionPreference = "Stop"

$backend = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/deep" -TimeoutSec 5
$frontend = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 5

[pscustomobject]@{
    backend_status = $backend.status
    backend_mode = $backend.mode
    source_status = $backend.source.status
    source_message = $backend.source.message
    frontend_status = $frontend.StatusCode
} | ConvertTo-Json
