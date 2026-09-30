#requires -Version 7.4
[CmdletBinding()]
param(
    [ValidateSet('Setup','Start','Worker','Test','CheckSmtp','Backup','ExportProductionConfig','SetPassword')]
    [string]$Action = 'Start',
    [string]$PythonExecutable,
    [string]$Username = 'moderator'
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.local/community/venv/Scripts/python.exe'
function Run([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "命令执行失败：$File" }
}
Push-Location $repo
try {
    if ($Action -eq 'Setup') {
        if (-not (Test-Path -LiteralPath $python)) {
            if (-not $PythonExecutable) {
                throw '首次初始化请指定 Python 3.12 或更新版本：-PythonExecutable 完整的python.exe路径。'
            }
            Run $PythonExecutable @('-m','venv','.local/community/venv')
        }
        Run $python @('-m','pip','install','-r','backend/requirements.txt')
        Run $python @('backend/tools/bootstrap.py','--repo',$repo)
        Run $python @('backend/manage.py','migrate','--noinput')
        Run $python @('backend/manage.py','collectstatic','--noinput')
        Run $python @('backend/manage.py','init_moderator','--username',$Username,'--credentials-file',"$repo/.local/community/admin-credentials.txt")
        Run $python @('backend/manage.py','check')
        Write-Host '初始化完成。管理员凭据：.local/community/admin-credentials.txt（请勿提交或分享）。'
        return
    }
    if (-not (Test-Path -LiteralPath $python)) { throw '请先执行 Setup。' }
    switch ($Action) {
        'Start' {
            $site = Join-Path $repo ('.local/community/site/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
            Run hugo @('--baseURL','http://127.0.0.1:8790/','--destination',$site)
            Run $python @('backend/manage.py','collectstatic','--noinput')
            Run $python @('backend/run_preview.py','--site',$site)
        }
        'Worker' { Run $python @('backend/manage.py','send_notifications','--loop') }
        'Test' { Run $python @('backend/manage.py','test','submissions','--verbosity','2') }
        'CheckSmtp' { Run $python @('backend/manage.py','check_smtp') }
        'Backup' { Run $python @('backend/manage.py','backup_database','--directory',"$repo/.local/community/backups") }
        'ExportProductionConfig' {
            Run $python @('backend/tools/bootstrap.py','--repo',$repo,'--production-config')
            Write-Host '生产配置：.local/community/production-config.json。包含凭据，请仅通过 SSH 传输。'
        }
        'SetPassword' { Run $python @('backend/manage.py','changepassword',$Username) }
    }
}
finally { Pop-Location }
