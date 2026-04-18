# Login
$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/token' -Method Post -Body @{username='admin';password='admin123'} -UseBasicParsing
$token = ($r.Content | ConvertFrom-Json).access_token
Write-Host "Login OK, role: $(($r.Content | ConvertFrom-Json).role)"

$headers = @{Authorization="Bearer $token"}

# Dashboard stats
$r2 = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/admin/dashboard-stats' -Headers $headers -UseBasicParsing
Write-Host "Dashboard: $($r2.Content)"

# System status (triggers model load)
$r3 = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/system/status' -UseBasicParsing
Write-Host "System Status: $($r3.Content)"

# List reference PDFs
$r4 = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/admin/pdfs' -Headers $headers -UseBasicParsing
Write-Host "Reference PDFs: $($r4.Content)"
