$ErrorActionPreference = "Stop"

$nginxRoot = "C:\nginx"
$nginxConfig = Join-Path $nginxRoot "conf\nginx.conf"
$posConfig = Join-Path $nginxRoot "conf\pos.conf"
$certificateDirectory = "C:\ProgramData\win-acme\certificates"
$certificate = Join-Path $certificateDirectory "testfarma24pos.ibsgroupbc365.com-chain.pem"
$certificateKey = Join-Path $certificateDirectory "testfarma24pos.ibsgroupbc365.com-key.pem"

if (-not (Test-Path $nginxConfig)) { throw "Nginx configuration not found: $nginxConfig" }
if (-not (Test-Path $certificate) -or -not (Test-Path $certificateKey)) {
    throw "POS TLS certificate files are missing. Issue the certificate before configuring Nginx."
}

$posHosts = @'
server {
    listen 443 ssl;
    server_name testfarma24pos.ibsgroupbc365.com;

    ssl_certificate     C:/ProgramData/win-acme/certificates/testfarma24pos.ibsgroupbc365.com-chain.pem;
    ssl_certificate_key C:/ProgramData/win-acme/certificates/testfarma24pos.ibsgroupbc365.com-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 25M;

    location /static/ { alias D:/ssl/django-projects/POS-test/staticfiles/; expires 30d; }
    location /media/ { alias D:/ssl/django-projects/POS-test/media/; }
    location / {
        proxy_pass http://127.0.0.1:8101;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300;
    }
}

server {
    listen 443 ssl;
    server_name farma24pos.ibsgroupbc365.com;

    ssl_certificate     C:/ProgramData/win-acme/certificates/testfarma24pos.ibsgroupbc365.com-chain.pem;
    ssl_certificate_key C:/ProgramData/win-acme/certificates/testfarma24pos.ibsgroupbc365.com-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 25M;

    location /static/ { alias D:/ssl/django-projects/POS-live/staticfiles/; expires 30d; }
    location /media/ { alias D:/ssl/django-projects/POS-live/media/; }
    location / {
        proxy_pass http://127.0.0.1:8102;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300;
    }
}
'@

$mainConfig = Get-Content $nginxConfig -Raw
if ($mainConfig -match 'include\s+conf/pos\.conf;') {
    $mainConfig = $mainConfig -replace 'include\s+conf/pos\.conf;', 'include pos.conf;'
}
if ($mainConfig -notmatch 'include\s+pos\.conf;') {
    $mainConfig = [regex]::Replace($mainConfig, '\s*}\s*$', "`r`n    include pos.conf;`r`n}`r`n")
    Set-Content -Path $nginxConfig -Value $mainConfig -NoNewline
}

Set-Content -Path $nginxConfig -Value $mainConfig -NoNewline

Set-Content -Path $posConfig -Value $posHosts -NoNewline
& (Join-Path $nginxRoot "nginx.exe") -p $nginxRoot -c "conf/nginx.conf" -t
if ($LASTEXITCODE -ne 0) { throw "Nginx configuration validation failed; Nginx was not reloaded." }

& (Join-Path $nginxRoot "nginx.exe") -p $nginxRoot -c "conf/nginx.conf" -s reload
if ($LASTEXITCODE -ne 0) { throw "Nginx reload failed." }
Write-Output "Nginx POS routes are active for testfarma24pos and farma24pos."