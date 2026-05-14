#Requires -Version 5.1
<#
.SYNOPSIS
    Lexa AI — Voice System Setup Script
.DESCRIPTION
    Downloads and configures the Piper TTS engine and German voice model
    for the Lexa AI assistant.
.NOTES
    Run from any directory: powershell -ExecutionPolicy Bypass -File scripts\setup_voice.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptDir   = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptDir          # lexa-ai/
$VoiceDir    = Join-Path $ProjectRoot "voice"
$PiperDir    = Join-Path $VoiceDir   "piper"
$PiperBinDir = Join-Path $PiperDir   "piper"          # voice/piper/piper/
$PiperExe    = Join-Path $PiperBinDir "piper.exe"
$ModelFile   = Join-Path $PiperDir   "de_mls_medium.onnx"
$ModelJson   = Join-Path $PiperDir   "de_mls_medium.onnx.json"

# ---------------------------------------------------------------------------
# Download URLs
# ---------------------------------------------------------------------------
$PiperZipUrl  = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
$ModelOnnxUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/mls/medium/de_DE-mls-medium.onnx"
$ModelJsonUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/mls/medium/de_DE-mls-medium.onnx.json"

# ---------------------------------------------------------------------------
# Summary tracking
# ---------------------------------------------------------------------------
$Summary = [ordered]@{
    "Piper Engine"   = "already present"
    "Voice Model"    = "already present"
    "Model Config"   = "already present"
}

# ---------------------------------------------------------------------------
# Helper: download with progress bar
# ---------------------------------------------------------------------------
function Get-FileWithProgress {
    param(
        [string]$Url,
        [string]$OutFile,
        [string]$Label
    )

    Write-Host ""
    Write-Host "  Downloading: " -NoNewline -ForegroundColor Cyan
    Write-Host $Label

    # Try to get file size first
    $fileSize = 0
    try {
        $headReq = [System.Net.HttpWebRequest]::Create($Url)
        $headReq.Method = "HEAD"
        $headReq.AllowAutoRedirect = $true
        $headReq.Timeout = 15000
        $headResp = $headReq.GetResponse()
        $fileSize = $headResp.ContentLength
        $headResp.Close()
    } catch {
        # If HEAD fails, proceed without size info
        $fileSize = -1
    }

    if ($fileSize -gt 0) {
        $sizeMB = [math]::Round($fileSize / 1MB, 1)
        Write-Host "  Size: ${sizeMB} MB" -ForegroundColor DarkGray
    }

    # Download with progress using HttpWebRequest for chunk-based progress
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = "GET"
        $request.AllowAutoRedirect = $true
        $request.Timeout = 300000  # 5 min timeout
        $response = $request.GetResponse()
        $totalBytes = $response.ContentLength
        $responseStream = $response.GetResponseStream()
        $outStream = [System.IO.File]::Create($OutFile)
        $buffer = New-Object byte[] 65536
        $bytesRead = 0
        $totalRead = 0
        $lastPercent = -1

        while (($bytesRead = $responseStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $outStream.Write($buffer, 0, $bytesRead)
            $totalRead += $bytesRead

            if ($totalBytes -gt 0) {
                $percent = [math]::Floor(($totalRead / $totalBytes) * 100)
                if ($percent -ne $lastPercent) {
                    $downloadedMB = [math]::Round($totalRead / 1MB, 1)
                    $totalMB = [math]::Round($totalBytes / 1MB, 1)
                    $barLen = 40
                    $filled = [math]::Floor($barLen * $percent / 100)
                    $empty = $barLen - $filled
                    $bar = ("#" * $filled) + ("-" * $empty)
                    Write-Host ("`r  [{0}] {1}% ({2}/{3} MB)" -f $bar, $percent, $downloadedMB, $totalMB) -NoNewline -ForegroundColor Yellow
                    $lastPercent = $percent
                }
            } else {
                $downloadedMB = [math]::Round($totalRead / 1MB, 1)
                Write-Host ("`r  Downloaded: {0} MB" -f $downloadedMB) -NoNewline -ForegroundColor Yellow
            }
        }

        Write-Host ""  # newline after progress bar
        $outStream.Close()
        $responseStream.Close()
        $response.Close()
    } catch {
        # Clean up partial file on error
        if ($outStream) { $outStream.Close() }
        if ($responseStream) { $responseStream.Close() }
        if ($response) { $response.Close() }
        if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
        throw
    }

    Write-Host "  Done." -ForegroundColor Green
}

# =========================================================================
# Main
# =========================================================================
Write-Host ""
Write-Host "=============================================" -ForegroundColor Magenta
Write-Host "  Lexa AI — Voice System Setup" -ForegroundColor Magenta
Write-Host "=============================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Project root : $ProjectRoot" -ForegroundColor DarkGray
Write-Host "  Voice dir    : $PiperDir" -ForegroundColor DarkGray
Write-Host ""

# Ensure directories exist
if (-not (Test-Path $PiperDir)) {
    Write-Host "[*] Creating directory: $PiperDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $PiperDir -Force | Out-Null
}

# ---------------------------------------------------------------------------
# 1. Piper Engine
# ---------------------------------------------------------------------------
Write-Host "[1/3] Piper TTS Engine" -ForegroundColor Cyan
if (Test-Path $PiperExe) {
    Write-Host "  piper.exe found — skipping download." -ForegroundColor Green
} else {
    Write-Host "  piper.exe not found — downloading..." -ForegroundColor Yellow
    $zipFile = Join-Path $PiperDir "piper_windows_amd64.zip"

    try {
        Get-FileWithProgress -Url $PiperZipUrl -OutFile $zipFile -Label "piper_windows_amd64.zip"

        Write-Host "  Extracting archive..." -ForegroundColor Cyan
        Expand-Archive -Path $zipFile -DestinationPath $PiperDir -Force
        Write-Host "  Extracted to: $PiperDir" -ForegroundColor Green

        # Clean up zip
        Remove-Item $zipFile -Force
        Write-Host "  Cleaned up zip file." -ForegroundColor DarkGray

        if (Test-Path $PiperExe) {
            $Summary["Piper Engine"] = "downloaded and extracted"
        } else {
            Write-Host "  WARNING: piper.exe not found after extraction!" -ForegroundColor Red
            Write-Host "  Expected at: $PiperExe" -ForegroundColor Red
            $Summary["Piper Engine"] = "FAILED — exe not found after extraction"
        }
    } catch {
        Write-Host "  ERROR downloading Piper: $($_.Exception.Message)" -ForegroundColor Red
        $Summary["Piper Engine"] = "FAILED — $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# 2. Voice Model (ONNX)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/3] German Voice Model (de_mls_medium — Piper Offline Fallback)" -ForegroundColor Cyan
if (Test-Path $ModelFile) {
    Write-Host "  Model file found — skipping download." -ForegroundColor Green
} else {
    Write-Host "  Model not found — downloading (~73 MB)..." -ForegroundColor Yellow
    try {
        Get-FileWithProgress -Url $ModelOnnxUrl -OutFile $ModelFile -Label "de_DE-mls-medium.onnx"
        $Summary["Voice Model"] = "downloaded"
    } catch {
        Write-Host "  ERROR downloading model: $($_.Exception.Message)" -ForegroundColor Red
        $Summary["Voice Model"] = "FAILED — $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# 3. Model Config JSON
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/3] Model Configuration" -ForegroundColor Cyan
if (Test-Path $ModelJson) {
    Write-Host "  Config file found — skipping download." -ForegroundColor Green
} else {
    Write-Host "  Config not found — downloading..." -ForegroundColor Yellow
    try {
        Get-FileWithProgress -Url $ModelJsonUrl -OutFile $ModelJson -Label "de_DE-mls-medium.onnx.json"
        $Summary["Model Config"] = "downloaded"
    } catch {
        Write-Host "  ERROR downloading config: $($_.Exception.Message)" -ForegroundColor Red
        $Summary["Model Config"] = "FAILED — $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# 4. Verify piper.exe
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[*] Verifying Piper installation..." -ForegroundColor Cyan
if (Test-Path $PiperExe) {
    try {
        $piperOutput = & $PiperExe --help 2>&1 | Select-Object -First 5
        Write-Host "  piper.exe responds to --help:" -ForegroundColor Green
        foreach ($line in $piperOutput) {
            Write-Host "    $line" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "  WARNING: piper.exe exists but could not be executed." -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "  SKIPPED — piper.exe not available." -ForegroundColor Red
}

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================" -ForegroundColor Magenta
Write-Host "  Setup Summary" -ForegroundColor Magenta
Write-Host "=============================================" -ForegroundColor Magenta
Write-Host ""

foreach ($item in $Summary.GetEnumerator()) {
    $icon = if ($item.Value -match "FAILED") { "X" } `
            elseif ($item.Value -eq "already present") { "=" } `
            else { "+" }

    $color = if ($item.Value -match "FAILED") { "Red" } `
             elseif ($item.Value -eq "already present") { "DarkGray" } `
             else { "Green" }

    Write-Host ("  [{0}] {1,-16} : {2}" -f $icon, $item.Key, $item.Value) -ForegroundColor $color
}

Write-Host ""

# Check if everything is ready
$allReady = (Test-Path $PiperExe) -and (Test-Path $ModelFile) -and (Test-Path $ModelJson)
if ($allReady) {
    Write-Host "  Voice system is ready!" -ForegroundColor Green
    Write-Host "  Piper: $PiperExe" -ForegroundColor DarkGray
    Write-Host "  Model: $ModelFile" -ForegroundColor DarkGray
} else {
    Write-Host "  Voice system is NOT fully configured." -ForegroundColor Red
    Write-Host "  Please check the errors above and re-run this script." -ForegroundColor Yellow
}

Write-Host ""
