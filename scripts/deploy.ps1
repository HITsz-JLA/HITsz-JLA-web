#requires -Version 7.4
[CmdletBinding()]
param(
    [ValidateSet('Deploy', 'Install', 'Status', 'Publish', 'Rollback', 'Cleanup')]
    [string]$Action = 'Deploy',
    [string]$ReleaseId,
    [string[]]$CheckPath = @('/', '/lyrics/', '/readings/', '/grammar/', '/participate/', '/search/', '/search-data.json'),
    [switch]$PrepareOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$repo = Split-Path -Parent $PSScriptRoot
$remote = 'root@hitszjla.club'
$sshOptions = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20',
    '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=111.228.7.90')

function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    $result = & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed (exit $LASTEXITCODE)." }
    return $result
}

function Invoke-Server {
    param([string]$Operation, [string]$Id = '', [string]$Checksum = '')
    $command = "jla-web-deploy $Operation"
    if ($Id) {
        if ($Id -notmatch '^\d{8}-\d{6}-\d{3}-[0-9a-f]{7,40}$') { throw 'Invalid release ID.' }
        $command += " $Id"
    }
    if ($Checksum) {
        if ($Checksum -notmatch '^[0-9a-f]{64}$') { throw 'Invalid checksum.' }
        $command += " --sha256 $Checksum"
    }
    $result = Invoke-Checked ssh ($sshOptions + @($remote, $command))
    return (($result -join "`n") | ConvertFrom-Json -AsHashtable)
}

function Write-DeploymentState {
    param([string]$Path, [hashtable]$Value)
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding utf8NoBOM
}

function Assert-CommunityReady {
    # The existing static publisher does not install or start the new backend.
    try {
        $health = Invoke-RestMethod -Uri 'https://hitszjla.club/community/api/health/' -TimeoutSec 15
        if ($health.ok -ne $true -or $health.service -ne 'jla-community' -or $health.api_version -ne 1) {
            throw 'Unexpected community API response.'
        }
    }
    catch {
        throw 'Community backend is not ready. Follow scripts/COMMUNITY.md to install the backend and Nginx route before publishing the frontend.'
    }
}

Push-Location $repo
try {
    if ($Action -eq 'Install') {
        $serverSource = Join-Path $PSScriptRoot 'server_deploy.py'
        $hash = (Get-FileHash -LiteralPath $serverSource -Algorithm SHA256).Hash.ToLowerInvariant()
        $token = [guid]::NewGuid().ToString('N')
        $remoteFile = "/tmp/jla-web-deploy-$token.py"
        Invoke-Checked scp ($sshOptions + @($serverSource, "${remote}:$remoteFile")) | Out-Host
        $install = @'
set -eu
echo '__HASH__  __FILE__' | sha256sum -c -
python3 '__FILE__' --help >/dev/null
mkdir -p /var/www/HITsz-JLA-web/.deploy/tool-backups
if [ -e /usr/local/sbin/jla-web-deploy ]; then
  cp -p /usr/local/sbin/jla-web-deploy '/var/www/HITsz-JLA-web/.deploy/tool-backups/__TOKEN__.py'
fi
install -o root -g root -m 755 '__FILE__' /usr/local/sbin/jla-web-deploy
rm -f -- '__FILE__'
'@
        $install = $install.Replace('__HASH__', $hash).Replace('__FILE__', $remoteFile).Replace('__TOKEN__', $token).Replace("`r", '')
        Invoke-Checked ssh ($sshOptions + @($remote, $install)) | Out-Host
        Invoke-Server status | ConvertTo-Json -Depth 8
        return
    }

    if ($Action -ne 'Deploy') {
        if ($Action -ne 'Status' -and -not $ReleaseId) { throw '-ReleaseId is required.' }
        if ($Action -eq 'Publish') { Assert-CommunityReady }
        $result = Invoke-Server $Action.ToLowerInvariant() $ReleaseId
        $result | ConvertTo-Json -Depth 10
        return
    }
    if ($ReleaseId) { throw 'Deploy generates a fresh ID; do not specify -ReleaseId.' }

    Get-Command git, hugo, ssh, scp -ErrorAction Stop | Out-Null
    $hugoVersion = (Invoke-Checked hugo @('version')) -join ' '
    if ($hugoVersion -notmatch 'v0\.152\.2-.*\+extended') {
        throw 'This deployment requires Hugo Extended 0.152.2, matching production.'
    }
    $dirty = @(Invoke-Checked git @('status', '--porcelain', '--untracked-files=no'))
    if ($dirty.Count) { throw 'Commit and push tracked changes before deploying.' }
    # Untracked files never enter git archive. Refuse unpublished content to avoid omissions.
    $untrackedContent = @(Invoke-Checked git @('ls-files', '--others', '--exclude-standard', '--',
        'content', 'static', 'assets', 'layouts', 'archetypes'))
    if ($untrackedContent.Count) { throw 'Untracked site content exists. Commit and push it first.' }
    $commit = (Invoke-Checked git @('rev-parse', 'HEAD')).Trim()
    $remoteHead = (Invoke-Checked git @('ls-remote', 'origin', 'refs/heads/main')) -join ''
    if (($remoteHead -split '\s+')[0] -ne $commit) { throw 'HEAD differs from GitHub origin/main. Synchronize first.' }
    Assert-CommunityReady
    $serverStatus = Invoke-Server status
    Write-Host "Current server release: $($serverStatus.current)"

    $id = "$(Get-Date -Format 'yyyyMMdd-HHmmss-fff')-$($commit.Substring(0,7))"
    $work = Join-Path $repo ".local/deploy/$id"
    $source = Join-Path $work 'source'
    $build = Join-Path $work 'build'
    New-Item -ItemType Directory -Path $work | Out-Null
    $stateFile = Join-Path $work 'deployment.json'
    $localState = @{id=$id; commit=$commit; phase='building'; build=$build}
    Write-DeploymentState $stateFile $localState
    Write-Host "Release ID: $id"

    # Build exactly the pushed commit, excluding working files and local caches.
    $sourceZip = Join-Path $work 'source.zip'
    Invoke-Checked git @('archive', '--format=zip', "--output=$sourceZip", $commit) | Out-Host
    [System.IO.Compression.ZipFile]::ExtractToDirectory($sourceZip, $source)
    $tree = @(Invoke-Checked git @('ls-tree', '-r', $commit))
    $submoduleIndex = 0
    foreach ($line in $tree) {
        if ($line -match '^160000 commit ([0-9a-f]{40})\t(.+)$') {
            $subCommit = $Matches[1]
            $subPath = $Matches[2]
            $subZip = Join-Path $work "submodule-$submoduleIndex.zip"
            $submoduleIndex++
            Invoke-Checked git @('-C', (Join-Path $repo $subPath), 'archive', '--format=zip', "--output=$subZip", $subCommit) | Out-Host
            [System.IO.Compression.ZipFile]::ExtractToDirectory($subZip, (Join-Path $source $subPath), $true)
        }
    }
    Invoke-Checked hugo @('--source', $source, '--destination', $build,
        '--baseURL', 'https://hitszjla.club/', '--environment', 'production', '--minify') | Out-Host

    # Validate the exact archived build before any release upload is requested.
    $validatorPython = Join-Path $repo '.local/community/venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $validatorPython)) {
        $pythonCommand = Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $pythonCommand) { throw 'Python 3 is required for the production output check.' }
        $validatorPython = $pythonCommand.Source
    }
    Invoke-Checked $validatorPython @((Join-Path $source 'scripts/check_site.py'), $build) | Out-Host

    $files = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $build -Recurse -File | Sort-Object FullName) {
        if ($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Build contains a symbolic link.' }
        $name = [System.IO.Path]::GetRelativePath($build, $file.FullName).Replace('\', '/')
        $files[$name] = @{size=$file.Length; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $checks = @()
    foreach ($route in $CheckPath) {
        if ($route -match '[?#\\]' -or $route.Contains('..')) { throw 'CheckPath must be a local website path.' }
        $checkFile = $route.Trim('/')
        if (-not $checkFile -or $route.EndsWith('/') -or -not [System.IO.Path]::HasExtension($checkFile)) {
            $checkFile = if ($checkFile) { "$checkFile/index.html" } else { 'index.html' }
        }
        if (-not $files.Contains($checkFile)) { throw "Health-check page was not generated: $checkFile" }
        $checks += $checkFile
    }
    $manifest = @{schema=1; commit=$commit; hugo=$hugoVersion; check_files=@($checks); files=$files}
    $manifestPath = Join-Path $work 'manifest.json'
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM

    $begin = Invoke-Server begin $id
    $incoming = $begin.incoming
    Invoke-Checked scp ($sshOptions + @($manifestPath, "${remote}:$incoming/manifest.json")) | Out-Host
    $plan = Invoke-Server plan $id
    $needed = @($plan.needed)
    Write-Host "Reuse $($plan.reused_files) files; upload $($needed.Count) changed/new files ($([math]::Round($plan.new_bytes / 1MB, 2)) MiB before compression)."

    # .NET PAX archives preserve Chinese/Japanese paths; no external tar command needed.
    $archive = Join-Path $work 'delta.tar.gz'
    $stream = $null
    $gzip = $null
    $writer = $null
    try {
        $stream = [System.IO.File]::Create($archive)
        $gzip = [System.IO.Compression.GZipStream]::new($stream, [System.IO.Compression.CompressionLevel]::Fastest, $true)
        $writer = [System.Formats.Tar.TarWriter]::new($gzip, [System.Formats.Tar.TarEntryFormat]::Pax, $true)
        foreach ($name in $needed) {
            if (-not $files.Contains($name)) { throw 'Server requested a file outside the manifest.' }
            $writer.WriteEntry((Join-Path $build $name), $name)
        }
    }
    finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $gzip) { $gzip.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
    $archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $localState.phase = 'uploading'
    Write-DeploymentState $stateFile $localState
    Invoke-Checked scp ($sshOptions + @($archive, "${remote}:$incoming/delta.tar.gz")) | Out-Host
    $prepared = Invoke-Server prepare $id $archiveHash
    $localState.phase = 'prepared'
    $localState.server = $prepared
    Write-DeploymentState $stateFile $localState
    if ($PrepareOnly) {
        Write-Host 'Prepared and verified. The live website has NOT been switched.'
        Write-Host "Publish: pwsh -File .\scripts\deploy.ps1 -Action Publish -ReleaseId $id"
        return
    }
    $result = Invoke-Server publish $id
    $localState.phase = 'published'
    $localState.server = $result
    Write-DeploymentState $stateFile $localState
    $result | ConvertTo-Json -Depth 8
    Write-Host "Deployment complete. Rollback: pwsh -File .\scripts\deploy.ps1 -Action Rollback -ReleaseId $id"
}
finally {
    Pop-Location
}
