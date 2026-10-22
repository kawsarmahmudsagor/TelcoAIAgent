# Keeps frontend\.env.local's LIVEKIT_URL pointed at this machine's current LAN IP.
# DHCP can hand out a new address between runs, which leaves the browser dialling a
# dead ws://<old-ip>:7880. Only rewrites an active line of the form
# LIVEKIT_URL=ws://<private-ip>:<port>; wss:// / localhost / cloud URLs are left alone.
#
# -PrintIp: print only the detected IP (for run-local.bat to pass to LiveKit's
# --node-ip) and change nothing.
param([string]$EnvFile = "frontend\.env.local", [switch]$PrintIp)

$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
    Sort-Object { $_.RouteMetric + $_.InterfaceMetric } | Select-Object -First 1
if (-not $route) { Write-Host "[WARN] No default route; LIVEKIT_URL left unchanged."; exit 0 }

$ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
if (-not $ip) { Write-Host "[WARN] Could not detect LAN IP; LIVEKIT_URL left unchanged."; exit 0 }

if ($PrintIp) { Write-Output $ip; exit 0 }

$pattern ='^(LIVEKIT_URL=ws://)(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)[\d.]+(:\d+)\s*$'
$lines = Get-Content $EnvFile
$changed = $false
$out = foreach ($l in $lines) {
    if ($l -match $pattern) {
        $new = "LIVEKIT_URL=ws://${ip}$($Matches[4])"
        if ($new -ne $l) { $changed = $true }
        $new
    } else { $l }
}
if ($changed) {
    Set-Content -Path $EnvFile -Value $out -Encoding utf8
    Write-Host "LIVEKIT_URL updated to ws://${ip} in $EnvFile"
} else {
    Write-Host "LIVEKIT_URL already matches LAN IP $ip (or is not a LAN ws:// URL)."
}
