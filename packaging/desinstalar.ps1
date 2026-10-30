$destino = Join-Path $env:LOCALAPPDATA 'Programs\Hoth Solutions'
Get-Process 'Hoth Solutions' -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Hoth Solutions.lnk') -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Hoth Solutions.lnk') -ErrorAction SilentlyContinue
Remove-Item $destino -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Hoth Solutions removido. A planilha e as versões (BKP) não foram apagadas.'
