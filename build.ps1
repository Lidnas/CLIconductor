param(
  [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = "C:\Users\user\AppData\Local\Python\pythoncore-3.12-64\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# 1. tests
& $py -m pytest
if ($LASTEXITCODE -ne 0) { throw "tests failed" }

# 2. frozen build
& $py -m PyInstaller --clean --noconfirm conductor.spec
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

# denylist guard: fail if mock module or denylist strings present in bundle
$bundle = "dist\conductor"
if (Test-Path "$bundle\conductor\adapters\mock.py") { throw "mock module shipped" }
$deny = @("mock completed", "demo_run", "fake_agent", "lorem")
foreach ($f in (Get-ChildItem $bundle -Recurse -File)) {
  try {
    $c = [System.IO.File]::ReadAllText($f.FullName)
    foreach ($d in $deny) {
      if ($c -match [regex]::Escape($d)) { throw "denylist hit: $d in $($f.FullName)" }
    }
  } catch {}
}

# smoke test frozen exe
$exe = "dist\conductor\conductor.exe"
& $exe --version
if ($LASTEXITCODE -ne 0) { throw "smoke --version failed" }
& $exe doctor
if ($LASTEXITCODE -ne 0) { throw "smoke doctor failed" }
# smoke: no-args (defaults to ui) with --no-browser
$port = 8199
$proc = Start-Process -FilePath $exe -ArgumentList "--no-browser","--port",$port -PassThru -RedirectStandardOutput "dist\smoke.out" -RedirectStandardError "dist\smoke.err"
Start-Sleep -Seconds 6
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 5
  if ($r.StatusCode -ne 200) { throw "smoke health failed" }
} finally {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

# 3. installer
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
& $iscc "installer.iss"
if ($LASTEXITCODE -ne 0) { throw "iscc failed" }

# 4. checksums
$installer = "dist\CLIConductor-Setup-$Version.exe"
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash
"$hash  $(Split-Path $installer -Leaf)" | Out-File -Encoding ascii "dist\SHA256SUMS.txt"
Write-Host "Built $installer"
Write-Host "SHA256: $hash"