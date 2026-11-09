$destino = Join-Path $env:LOCALAPPDATA 'Programs\Hoth Finance'
Get-Process 'Hoth Finance' -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Hoth Finance.lnk') -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Hoth Finance.lnk') -ErrorAction SilentlyContinue
Remove-Item $destino -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Hoth Finance removido. A planilha e as versões (BKP) não foram apagadas.'
