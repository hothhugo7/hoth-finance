# Instalador do Hoth Solutions (não precisa de administrador).
# Instala em %LOCALAPPDATA%\Programs\Hoth Solutions, verifica as dependências e cria os atalhos.
$ErrorActionPreference = 'Stop'
$origem = Split-Path -Parent $MyInvocation.MyCommand.Path
$destino = Join-Path $env:LOCALAPPDATA 'Programs\Hoth Solutions'
$redePadrao = '\\servidor\financeiro\FECHAMENTO FINANCEIRO\2026\Hoth\Hoth - Fechamento Financeiro Exemplo 2026.xlsx'

function Titulo($t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }

Write-Host 'HOTH SOLUTIONS - Instalação' -ForegroundColor White
Titulo 'Verificando o computador'

# 1. Excel desktop (obrigatório: é ele que grava na planilha)
$excel = Test-Path 'Registry::HKEY_CLASSES_ROOT\Excel.Application'
if ($excel) { Write-Host '[ok] Microsoft Excel encontrado' -ForegroundColor Green }
else { Write-Host '[!] Microsoft Excel NÃO encontrado. O app abre, mas não consegue gravar na planilha sem o Excel.' -ForegroundColor Yellow }

# 2. Edge WebView2 (janela do app). Sem ele o app abre no navegador.
$chaves = @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
            'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
            'HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
$wv2 = $chaves | Where-Object { (Test-Path $_) -and ((Get-ItemProperty $_ -ErrorAction SilentlyContinue).pv -notin @($null, '', '0.0.0.0')) }
if ($wv2) { Write-Host '[ok] Microsoft Edge WebView2 encontrado' -ForegroundColor Green }
else {
    Write-Host '[..] Instalando o Microsoft Edge WebView2 (precisa de internet)...'
    $setup = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
    $local = Join-Path $origem 'MicrosoftEdgeWebview2Setup.exe'
    try {
        if (Test-Path $local) { Copy-Item $local $setup -Force }
        else { Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $setup -UseBasicParsing }
        Start-Process $setup -ArgumentList '/silent /install' -Wait
        Write-Host '[ok] WebView2 instalado' -ForegroundColor Green
    } catch {
        Write-Host '[!] Não consegui instalar o WebView2. O app vai abrir no navegador.' -ForegroundColor Yellow
    }
}

# 3. Copia o programa (preserva hoth.json e Dados de uma instalação anterior)
Titulo "Instalando em $destino"
$app = Join-Path $origem 'Hoth Solutions'
Get-Process 'Hoth Solutions' -ErrorAction SilentlyContinue | Stop-Process -Force
New-Item -ItemType Directory -Force $destino | Out-Null
$configAntiga = Join-Path $destino 'hoth.json'
$tinhaConfig = Test-Path $configAntiga
robocopy $app $destino /E /NFL /NDL /NJH /NJS /NP /XF hoth.json /XD Dados | Out-Null
New-Item -ItemType Directory -Force (Join-Path $destino 'Dados') | Out-Null
Write-Host '[ok] Programa copiado' -ForegroundColor Green

# 4. Onde fica a planilha
Titulo 'Planilha'
if ($tinhaConfig) {
    Write-Host '[ok] Mantida a configuração da instalação anterior (hoth.json).' -ForegroundColor Green
} else {
    $planilhaPacote = Get-ChildItem (Join-Path $origem 'Planilha') -Filter *.xlsx -ErrorAction SilentlyContinue | Select-Object -First 1
    $temRede = Test-Path $redePadrao
    $aviso = if ($temRede) { '' } else { '  (não acessível agora)' }
    Write-Host "  1 - Usar a planilha oficial da rede: $redePadrao$aviso"
    Write-Host '  2 - Usar a planilha que vem no pacote, instalada neste computador'
    $op = Read-Host 'Escolha 1 ou 2 [1]'
    if ($op -eq '2' -and $planilhaPacote) {
        $pasta = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Hoth Solutions'
        New-Item -ItemType Directory -Force (Join-Path $pasta 'BKP') | Out-Null
        $alvo = Join-Path $pasta $planilhaPacote.Name
        if (-not (Test-Path $alvo)) { Copy-Item $planilhaPacote.FullName $alvo }
        $regras = Join-Path $planilhaPacote.DirectoryName 'Regras fixas.json'
        if ((Test-Path $regras) -and -not (Test-Path (Join-Path $pasta 'Regras fixas.json'))) { Copy-Item $regras $pasta }
        $planilha = $alvo; $bkp = Join-Path $pasta 'BKP'
    } else {
        $planilha = $redePadrao; $bkp = Join-Path (Split-Path $redePadrao) 'BKP'
    }
    $cfg = [ordered]@{
        planilha = $planilha; pasta_bkp = $bkp; manter_backups = 60
        pasta_comprovantes = '\\servidor\financeiro\FECHAMENTO FINANCEIRO\Comprovantes de pagamento Santander'
    }
    [IO.File]::WriteAllText($configAntiga, ($cfg | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Write-Host "[ok] Planilha: $planilha" -ForegroundColor Green
}

# 5. Atalhos
$exe = Join-Path $destino 'Hoth Solutions.exe'
$ws = New-Object -ComObject WScript.Shell
foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Hoth Solutions.lnk'),
                   (Join-Path ([Environment]::GetFolderPath('Programs')) 'Hoth Solutions.lnk'))) {
    $s = $ws.CreateShortcut($lnk); $s.TargetPath = $exe; $s.WorkingDirectory = $destino; $s.IconLocation = $exe; $s.Save()
}
Write-Host '[ok] Atalhos criados na Área de Trabalho e no Menu Iniciar' -ForegroundColor Green

Titulo 'Pronto'
Write-Host 'Abra pelo atalho "Hoth Solutions". Para desinstalar: Desinstalar.bat (a planilha não é apagada).'
