<#
.SYNOPSIS
    Installs, updates or removes Racing Dashboard on Windows.

.DESCRIPTION
    Racing Dashboard shows live data of PC racing games on your phone and tablet.
    This script sets everything up:
      1. Python 3.12 or newer (installs Python 3.13 with winget if needed)
      2. the Racing Dashboard files (downloads them when run from the internet)
      3. a check that everything loads
      4. the Windows firewall rule so phones and tablets can connect (one admin prompt)
      5. shortcuts on the desktop and in the Start menu
    Your own settings (config\config.toml) are kept on an update.

    Install or update from the internet, in PowerShell:
        irm https://raw.githubusercontent.com/AlexanderHultsch/Racing-Dashboard/main/tools/install.ps1 | iex

    From a downloaded copy: double-click install.bat.
    Remove: Start menu > Racing Dashboard > Uninstall Racing Dashboard.

.PARAMETER InstallDir
    Where to install. Default: the downloaded copy the script is in, otherwise
    %LOCALAPPDATA%\RacingDashboard.
.PARAMETER Uninstall
    Removes the shortcuts and the firewall rule, and the program folder if this script downloaded it.
.PARAMETER Yes
    Answers every question with its default (unattended install).
.PARAMETER NoShortcuts
    Does not create shortcuts.
.PARAMETER NoFirewall
    Does not add the firewall rule.
.PARAMETER PauseAtEnd
    Waits for Enter before the window closes (used by the Start menu uninstall shortcut).
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$Uninstall,
    [switch]$Yes,
    [switch]$NoShortcuts,
    [switch]$NoFirewall,
    [switch]$PauseAtEnd
)

# Note: this script must stay plain ASCII and Windows PowerShell 5.1 compatible, and must never
# call "exit": run through "irm | iex" that would close the user's PowerShell window.

$RD_Repo = "AlexanderHultsch/Racing-Dashboard"
$RD_Name = "Racing Dashboard"
$RD_MinPython = 312
$RD_Marker = ".installed-by-script"
$RD_CodeFolders = @("core", "ui", "games", "docs", "tools", "tests")

# ---------------------------------------------------------------- output helpers

function Write-Title([string]$text) {
    Write-Host ""
    Write-Host ("=" * 64) -ForegroundColor DarkCyan
    Write-Host "  $text" -ForegroundColor White
    Write-Host ("=" * 64) -ForegroundColor DarkCyan
}
function Write-Step([int]$number, [int]$total, [string]$text) {
    Write-Host ""
    Write-Host "[$number/$total] $text" -ForegroundColor Cyan
}
function Write-Ok([string]$text)   { Write-Host "  OK     $text" -ForegroundColor Green }
function Write-Info([string]$text) { Write-Host "         $text" -ForegroundColor Gray }
function Write-Note([string]$text) { Write-Host "  NOTE   $text" -ForegroundColor Yellow }
function Write-Bad([string]$text)  { Write-Host "  ERROR  $text" -ForegroundColor Red }

function Confirm-Choice([string]$question, [bool]$default = $true) {
    if ($Yes) { return $default }
    $hint = if ($default) { "[Y/n]" } else { "[y/N]" }
    $answer = Read-Host "  $question $hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim().ToLower().StartsWith("y") -or $answer.Trim().ToLower().StartsWith("j")
}

# ---------------------------------------------------------------- Python

function Get-PythonInfo([string]$exe, [string[]]$prefix) {
    # Runs a Python candidate and returns version and real path, or $null.
    $ErrorActionPreference = "Continue"
    try {
        $code = "import sys; print(sys.version_info[0] * 100 + sys.version_info[1]); print(sys.executable)"
        $out = & $exe @prefix -c $code 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $lines = @($out)
        if ($lines.Count -lt 2) { return $null }
        return [pscustomobject]@{ Version = [int]$lines[0]; Path = $lines[1].Trim() }
    } catch {
        return $null
    }
}

function Format-PythonVersion([int]$version) {
    return "{0}.{1}" -f [math]::Floor($version / 100), ($version % 100)
}

function Find-Python {
    $found = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $found += Get-PythonInfo "py" @("-3")
    }
    foreach ($name in @("python", "python3")) {
        foreach ($command in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
            $found += Get-PythonInfo $command.Source @()
        }
    }
    foreach ($root in @("$env:LOCALAPPDATA\Programs\Python", $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($root -and (Test-Path $root)) {
            foreach ($folder in @(Get-ChildItem $root -Directory -Filter "Python3*" -ErrorAction SilentlyContinue)) {
                $exe = Join-Path $folder.FullName "python.exe"
                if (Test-Path $exe) { $found += Get-PythonInfo $exe @() }
            }
        }
    }
    $usable = @($found | Where-Object { $_ -and $_.Version -ge $RD_MinPython -and (Test-Path $_.Path) })
    if ($usable.Count -gt 0) {
        return ($usable | Sort-Object Version -Descending | Select-Object -First 1)
    }
    $old = @($found | Where-Object { $_ } | Sort-Object Version -Descending | Select-Object -First 1)
    if ($old.Count -gt 0) {
        Write-Note ("Found Python {0}, but Racing Dashboard needs 3.12 or newer." -f (Format-PythonVersion $old[0].Version))
    }
    return $null
}

function Install-Python {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing Python 3.13 for your user with winget. This can take a minute ..."
        & winget install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        return (Find-Python)
    }
    Write-Bad "winget (the Windows package manager) is not available on this PC."
    Write-Info "Please install Python yourself:"
    Write-Info "  1. The download page opens now: choose the latest 'Windows installer (64-bit)'."
    Write-Info "  2. In the installer tick 'Add python.exe to PATH', then 'Install Now'."
    Write-Info "  3. Run this installer again."
    Start-Process "https://www.python.org/downloads/windows/"
    return $null
}

# ---------------------------------------------------------------- files

function Get-ProgramFiles([string]$target) {
    # Downloads the latest version from GitHub into $target; keeps config\ and logs\.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $temp = Join-Path $env:TEMP ("racing-dashboard-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $temp | Out-Null
    try {
        $zip = Join-Path $temp "main.zip"
        $ProgressPreference = "SilentlyContinue"   # the progress bar makes Invoke-WebRequest very slow
        Write-Info "Downloading from github.com/$RD_Repo ..."
        Invoke-WebRequest -Uri "https://github.com/$RD_Repo/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $temp -Force
        $source = Get-ChildItem $temp -Directory | Select-Object -First 1
        if (-not (Test-Path (Join-Path $source.FullName "core\server.py"))) { throw "The download does not contain Racing Dashboard." }
        if (Test-Path $target) {
            foreach ($folder in $RD_CodeFolders) {
                $path = Join-Path $target $folder
                if (Test-Path $path) { Remove-Item $path -Recurse -Force }
            }
        } else {
            New-Item -ItemType Directory -Path $target | Out-Null
        }
        # robocopy merges into the existing folder and keeps files that are not in the download (config.toml)
        & robocopy $source.FullName $target /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Copying the files failed (robocopy code $LASTEXITCODE)." }
        Set-Content -Path (Join-Path $target $RD_Marker) -Value "Installed by tools\install.ps1. Uninstall may delete this folder." -Encoding ASCII
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------- firewall and network

function Invoke-Elevated([string]$command) {
    # Runs a PowerShell command as administrator (one Windows prompt). Returns $true if it ran.
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    try {
        $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
        return ($process.ExitCode -eq 0)
    } catch {
        return $false
    }
}

function Get-RulePort {
    $rule = Get-NetFirewallRule -DisplayName $RD_Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $rule) { return $null }
    return [string](($rule | Get-NetFirewallPortFilter).LocalPort)
}

function Add-FirewallRule([int]$port) {
    if ((Get-RulePort) -eq [string]$port) {
        Write-Ok "Firewall rule for port $port already exists."
        return
    }
    Write-Info "Phones and tablets connect to this PC on port $port. Windows needs a firewall rule for that."
    if (-not (Confirm-Choice "Add the firewall rule now? (Windows asks for admin rights once)")) {
        Write-Note "Skipped. When the dashboard starts the first time, Windows may ask: allow Python on private networks."
        return
    }
    $command = "Remove-NetFirewallRule -DisplayName '$RD_Name' -ErrorAction SilentlyContinue; " +
               "New-NetFirewallRule -DisplayName '$RD_Name' -Description 'Lets phones and tablets in the local network open Racing Dashboard.' " +
               "-Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Private,Domain | Out-Null"
    if ((Invoke-Elevated $command) -and ((Get-RulePort) -eq [string]$port)) {
        Write-Ok "Firewall rule added (TCP port $port, private networks)."
    } else {
        Write-Note "The firewall rule was not added (admin prompt declined?). Windows may ask when the dashboard starts: allow Python on private networks."
    }
}

function Test-NetworkProfile {
    $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
    $public = @($profiles | Where-Object { $_.NetworkCategory -eq "Public" })
    if ($public.Count -eq 0) {
        if ($profiles.Count -gt 0) { Write-Ok "Your network is private: phones and tablets can connect." }
        return
    }
    foreach ($network in $public) {
        Write-Note "Your network '$($network.Name)' is set to Public. Windows blocks phones and tablets on public networks."
    }
    if (Confirm-Choice "Set your home network to Private now? (admin prompt; only do this at home, not on public Wi-Fi)") {
        $indexes = ($public | ForEach-Object { $_.InterfaceIndex }) -join ","
        if (Invoke-Elevated "Set-NetConnectionProfile -InterfaceIndex $indexes -NetworkCategory Private") {
            Write-Ok "Network set to Private."
        } else {
            Write-Note "Not changed. Do it in Settings > Network & internet > your connection > Private network."
        }
    } else {
        Write-Info "You can change it later: Settings > Network & internet > your connection > Private network."
    }
}

# ---------------------------------------------------------------- shortcuts

function Get-ShortcutPaths {
    $startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) $RD_Name
    $desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "$RD_Name.lnk"
    return [pscustomobject]@{ StartMenu = $startMenu; Desktop = $desktop }
}

function New-Shortcut([string]$path, [string]$target, [string]$arguments, [string]$workDir, [string]$icon, [string]$description) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $workDir
    if ($icon -and (Test-Path $icon)) { $link.IconLocation = "$icon,0" }
    $link.Description = $description
    $link.Save()
}

function Add-Shortcuts([string]$dir, [string]$python) {
    $paths = Get-ShortcutPaths
    $server = Join-Path $dir "core\server.py"
    $icon = Join-Path $dir "ui\icon.ico"
    New-Item -ItemType Directory -Path $paths.StartMenu -Force | Out-Null
    New-Shortcut (Join-Path $paths.StartMenu "$RD_Name.lnk") $python "`"$server`"" $dir $icon "Start Racing Dashboard"
    New-Shortcut (Join-Path $paths.StartMenu "Uninstall $RD_Name.lnk") "powershell.exe" `
        "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $dir 'tools\install.ps1')`" -Uninstall -PauseAtEnd" $dir "" "Remove Racing Dashboard"
    New-Shortcut (Join-Path $paths.StartMenu "$RD_Name folder.lnk") $dir "" $dir "" "Open the Racing Dashboard folder (settings: config)"
    Write-Ok "Start menu: $RD_Name"
    if (Confirm-Choice "Create a desktop shortcut?") {
        New-Shortcut $paths.Desktop $python "`"$server`"" $dir $icon "Start Racing Dashboard"
        Write-Ok "Desktop shortcut created."
    }
}

# ---------------------------------------------------------------- install

function Install-RacingDashboard {
    $total = 5
    Write-Title "$RD_Name - installer"
    Write-Info "Live data of PC racing games on your phone and tablet."
    Write-Info "This sets up Python, the program, the firewall and shortcuts. Nothing is sent anywhere."

    # Where: the copy this script belongs to, or the default folder.
    $localCopy = $null
    if ($PSScriptRoot) {
        $parent = Split-Path $PSScriptRoot -Parent
        if (Test-Path (Join-Path $parent "core\server.py")) { $localCopy = $parent }
    }
    if (-not $InstallDir) {
        if ($localCopy) { $InstallDir = $localCopy } else { $InstallDir = Join-Path $env:LOCALAPPDATA "RacingDashboard" }
    }
    $InstallDir = [IO.Path]::GetFullPath($InstallDir)

    # 1. Python
    Write-Step 1 $total "Python"
    $python = Find-Python
    if (-not $python) {
        Write-Note "Python 3.12 or newer is needed and was not found."
        if (-not (Confirm-Choice "Install Python 3.13 now?")) {
            Write-Bad "Racing Dashboard cannot run without Python. Nothing was changed."
            return $false
        }
        $python = Install-Python
        if (-not $python) {
            Write-Bad "Python could not be installed automatically. Nothing else was changed."
            return $false
        }
    }
    Write-Ok ("Python {0}  ({1})" -f (Format-PythonVersion $python.Version), $python.Path)
    $pythonExe = $python.Path

    # 2. Files
    Write-Step 2 $total "Program files"
    $sameAsLocal = $localCopy -and ($InstallDir.TrimEnd("\") -ieq $localCopy.TrimEnd("\"))
    if ($sameAsLocal) {
        Write-Ok "Using this copy: $InstallDir"
        if (Test-Path (Join-Path $InstallDir ".git")) { Write-Info "Update it with 'git pull'." }
    } elseif (Test-Path (Join-Path $InstallDir ".git")) {
        Write-Ok "Using the git copy in $InstallDir (update it with 'git pull')."
    } else {
        $isUpdate = Test-Path (Join-Path $InstallDir "core\server.py")
        if ($isUpdate) { Write-Info "Updating $InstallDir (your settings in config\ are kept)." }
        else { Write-Info "Installing to $InstallDir" }
        try {
            Get-ProgramFiles $InstallDir
        } catch {
            Write-Bad "Download failed: $($_.Exception.Message)"
            Write-Info "Check the internet connection, or download the ZIP from https://github.com/$RD_Repo and run install.bat."
            return $false
        }
        if ($isUpdate) { Write-Ok "Updated to the latest version." } else { Write-Ok "Installed." }
    }
    Get-ChildItem $InstallDir -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

    # 3. Check
    Write-Step 3 $total "Check"
    $ErrorActionPreference = "Continue"
    $check = & $pythonExe (Join-Path $InstallDir "core\server.py") --check 2>&1 | ForEach-Object { "$_" }
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0 -or -not ($check -match "Result\s+OK")) {
        Write-Bad "The dashboard does not start:"
        $check | ForEach-Object { Write-Info $_ }
        return $false
    }
    $port = 8080
    $address = ""
    foreach ($line in $check) {
        if ($line -match "Web port\s+(\d+)") { $port = [int]$Matches[1] }
        if ($line -match "Address\s+(http\S+)") { $address = $Matches[1] }
        if ($line -match "Games\s+(.+)$") { Write-Ok "Games: $($Matches[1])" }
    }
    Write-Ok "Everything loads."

    # 4. Network
    Write-Step 4 $total "Network (so phones and tablets can connect)"
    if ($NoFirewall) { Write-Info "Skipped (-NoFirewall)." }
    else {
        try {
            Add-FirewallRule $port
            Test-NetworkProfile
        } catch {
            Write-Note "Could not check the firewall / network: $($_.Exception.Message)"
            Write-Info "If phones cannot connect: allow Python on private networks when Windows asks."
        }
    }

    # 5. Shortcuts
    Write-Step 5 $total "Shortcuts"
    if ($NoShortcuts) { Write-Info "Skipped (-NoShortcuts)." }
    else {
        try {
            Add-Shortcuts $InstallDir $pythonExe
        } catch {
            Write-Note "Shortcuts could not be created: $($_.Exception.Message)"
            Write-Info "Start the dashboard with start_dashboard.bat in $InstallDir"
        }
    }

    # Done
    Write-Title "Done - $RD_Name is installed"
    Write-Host "  Start it:  Start menu or desktop > $RD_Name" -ForegroundColor White
    Write-Host "  Then open on your phone or tablet (same Wi-Fi):" -ForegroundColor White
    Write-Host ""
    Write-Host "      $address" -ForegroundColor Green
    Write-Host "      Gear + Rev:  $address/gear      Dash:  $address/dash" -ForegroundColor Green
    Write-Host ""
    Write-Info "Tip: on the iPhone / iPad use Share > Add to Home Screen for full screen."
    Write-Info "No game at hand? Settings (gear button) > GAME > DEMO shows a simulated car."
    Write-Info "Assetto Corsa EVO: check the keys once, see README.md > ACE keys."
    Write-Info "Folder: $InstallDir"
    Write-Host ""
    if (Confirm-Choice "Start $RD_Name now?") {
        Start-Process -FilePath $pythonExe -ArgumentList "`"$(Join-Path $InstallDir 'core\server.py')`"" -WorkingDirectory $InstallDir
        Write-Ok "Started in a new window."
    }
    return $true
}

# ---------------------------------------------------------------- uninstall

function Uninstall-RacingDashboard {
    Write-Title "$RD_Name - uninstall"
    $dir = $InstallDir
    if (-not $dir -and $PSScriptRoot) { $dir = Split-Path $PSScriptRoot -Parent }
    if (-not $dir) { $dir = Join-Path $env:LOCALAPPDATA "RacingDashboard" }
    $dir = [IO.Path]::GetFullPath($dir)
    if (-not (Confirm-Choice "Remove $RD_Name (shortcuts and firewall rule)?")) {
        Write-Info "Nothing was changed."
        return $true
    }
    $paths = Get-ShortcutPaths
    if (Test-Path $paths.StartMenu) { Remove-Item $paths.StartMenu -Recurse -Force; Write-Ok "Start menu entries removed." }
    if (Test-Path $paths.Desktop) { Remove-Item $paths.Desktop -Force; Write-Ok "Desktop shortcut removed." }
    if (Get-RulePort) {
        if (Invoke-Elevated "Remove-NetFirewallRule -DisplayName '$RD_Name'") { Write-Ok "Firewall rule removed." }
        else { Write-Note "The firewall rule '$RD_Name' is still there (admin prompt declined). Remove it in Windows Defender Firewall if you like." }
    }
    if (Test-Path (Join-Path $dir $RD_Marker)) {
        if (Confirm-Choice "Also delete the program folder with your settings? ($dir)") {
            Set-Location $env:TEMP
            Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path $dir) { Write-Note "Some files are in use (is the dashboard still running?). Delete $dir by hand." }
            else { Write-Ok "Program folder deleted." }
        }
    } elseif (Test-Path (Join-Path $dir "core\server.py")) {
        Write-Info "The program folder was not installed by this script and stays: $dir"
    }
    Write-Info "Python stays installed (other programs may use it)."
    Write-Ok "$RD_Name is removed."
    return $true
}

# ---------------------------------------------------------------- main

function Invoke-RacingDashboardSetup {
    $ErrorActionPreference = "Stop"
    if ([Environment]::OSVersion.Platform -ne "Win32NT") {
        Write-Bad "This installer is for Windows. On other systems run: python3 core/server.py"
        return
    }
    try {
        # A PowerShell function returns all its output: the result is the last value.
        if ($Uninstall) { $result = @(Uninstall-RacingDashboard) } else { $result = @(Install-RacingDashboard) }
        $ok = ($result.Count -gt 0) -and ($result[-1] -eq $true)
        if (-not $ok) {
            Write-Host ""
            Write-Info "Need help? Open an issue: https://github.com/$RD_Repo/issues"
        }
    } catch {
        Write-Bad "Unexpected problem: $($_.Exception.Message)"
        Write-Info "Please report it with this text: https://github.com/$RD_Repo/issues"
    }
    if ($PauseAtEnd -and -not $Yes) {
        Write-Host ""
        Read-Host "  Press Enter to close" | Out-Null
    }
}

Invoke-RacingDashboardSetup
