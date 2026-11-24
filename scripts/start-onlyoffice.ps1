$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$linuxRoot='/mnt/'+$root.Substring(0,1).ToLower()+$root.Substring(2).Replace('\','/')
wsl -d Ubuntu -u root --cd $linuxRoot -- sh -c 'sh scripts/start-onlyoffice.sh && docker wait zhixi-onlyoffice'
if($LASTEXITCODE -ne 0){throw 'ONLYOFFICE startup failed'}
