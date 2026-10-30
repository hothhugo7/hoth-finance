# Hoth Solutions — Fechamento Financeiro

Planilha única de fechamento (DFC + DRE) alimentada por uma tabela só de lançamentos,
com plano de contas e grupos editáveis. Primeiro cliente: Supermercado Exemplo Ltda (2026).

## Abrir o app

Pacote: **`Pacote\Hoth Solutions\Hoth Solutions.exe`** (janela própria; veja o `LEIA-ME.txt` da pasta).
A partir do código: **`Abrir Hoth.bat`**. Funciona só neste computador (127.0.0.1). Telas:

- **Painel**: lançamentos, quantos estão sem classificação, última importação, versões guardadas.
- **Importar extrato**: arraste o extrato do Santander (.xlsx), o OFX da Cora ou o relatório de boletos pagos da
  lotérica exportado do RET (.xls). Revise as contas (verde = proposta, amarelo = revisar, sugestões em botões,
  "aplicar a parecidos") e clique em **Gravar na planilha**. A lotérica entra na Caixa Loja, um lançamento por boleto.
- **Colar Caixa Loja**: no CONTROLE DE CAIXA, copie as linhas (ou a aba inteira) e cole na tela. O app mostra só o que
  é a partir da data escolhida e ainda não está na Hoth, aponta possíveis correções e deixa a lotérica de fora
  (ela vem do RET). Corrija o que precisar e grave.
- **Contas a Pagar**: importe o relatório de contas em aberto do RET (.xls). O app guarda cada título (nunca apaga) e
  procura o pagamento em todos os bancos, na lotérica, nos comprovantes e nos malotes: pago e conferido, provável
  (confirmar), no malote, aguardando fatura, baixado no RET sem prova, vencido, a vencer. Os títulos ficam no arquivo
  `Hoth - Contas a Pagar e Fluxo 2026.xlsx`, ao lado da planilha oficial (que não é alterada).
- **Malote**: digite os valores da fita (Enter a cada um); o app acha o boleto no Contas a Pagar e acompanha o retorno.
- **Fatura do cartão**: lista sozinha as faturas em PDF da pasta (senha na configuração), acha o débito no extrato do
  Santander e troca essa linha pelas compras, cada uma com a sua conta, na data do débito. Dá para agrupar por
  estabelecimento e para desfazer. Reimportar o extrato não traz o débito de volta.
- **Categorias**: Mercadoria, Despesa, Financeiro (e as que você criar) por fornecedor; começa com o cadastro da
  versão Base e sugere pela conta do plano.
- **Fluxo de Caixa**: quanto entra e sai num período, por categoria e dia a dia (pago na data do pagamento, em aberto
  no vencimento, vencido hoje). Entradas são lançadas na tela. A planilha `Hoth - Fluxo de Caixa Projetado 2026.xlsx`
  é refeita sozinha a cada importação, malote, categoria ou entrada.
- **Lançamentos**: busca e filtros; selecione vários e reclassifique de uma vez.
- **Plano de contas**: criar, editar, renomear, mesclar, desativar e excluir contas; criar, editar e reordenar
  grupos. As alterações ficam num rascunho até **Aplicar na planilha**, que refaz DFC/DRE/DRE Manual.
- **Versões e auditoria**: as versões do BKP (com Restaurar) e o histórico da aba Auditoria.

Toda gravação exige a planilha fechada no Excel e guarda a versão anterior no BKP.

## Pastas

| Pasta | Conteúdo |
|---|---|
| Rede: `\\servidor\financeiro\FECHAMENTO FINANCEIRO\2026\Hoth\` | **Planilha oficial** e `BKP\` (versões anteriores, guardadas antes de cada gravação). Caminho definido no `hoth.json`; para mudar de lugar use `scripts\mover_planilha.py DESTINO` |
| `Relatorios/` | Relatórios das fases, situação da planilha, conferência da migração e piloto |
| `hoth/` | Código: leitura da planilha antiga, geração da planilha nova, conferência, leitores, classificação, gravação; `hoth/web/` = app |
| `scripts/` | `migrar_2026.py` (gera e confere), `importar.py` (prévia, gravação, backups e restauração), `avaliar_fase3.py` (mede a classificação), `atualizar_visual.py` (refaz o visual sem perder dados), `gerar_logos.py` (logos e ícone), `empacotar.py` (gera o pacote), `conferir_piloto.py` (piloto) e `copiar_caixa_loja.py` (obsoleto: use a tela Colar Caixa Loja) |
| `Pacote/` | App empacotado (`Hoth Solutions`) e ZIP datado |
| `frontend/` | Telas do app (React + TypeScript). `npm run build` gera `hoth/web/static` |
| `Dados/` | Extratos enviados pelo app (cópia do original) e rascunho do plano de contas |
| `tests/` | Testes automáticos (`.venv\Scripts\python.exe -m pytest tests`) |

## Como a planilha funciona

- **Lançamentos** (`tbLanc`): um lançamento por linha, de todos os bancos. Ano, Mês, Código e Grupo são fórmulas.
  A Conta é escolhida numa lista do Plano de Contas.
- **DFC** e **DRE**: somam `tbLanc` por **código da conta + ano + mês** (`SOMASES`). Não dependem do nome escrito.
- **DRE Manual**: grade conta × mês para os valores da DRE que são digitados (competência): faturamento da Curva ABC,
  CPV, pró-labore de cada sócio, tarifas das maquininhas. Contas marcadas "Valor na DRE = Manual" no Plano de Contas.
- **Ajustes DRE** (`tbAjustes`): outros acertos da DRE. `SUBSTITUI` troca o valor do mês da conta;
  `SOMA` acrescenta ao valor vindo dos lançamentos.
- **Orçamento** (`tbOrc`): coluna PREV da DRE.
- **Bancos** e **Saldos Informados**: saldo inicial do ano e saldo do extrato no início de cada mês; a DFC mostra a
  diferença entre o saldo calculado e o informado.
- Linhas de controle da DFC: *Sem classificação*, *Conta inválida* e *Diferença* (deve ser zero).
- Visual: capa com indicadores dos meses fechados e botões de navegação; DFC e DRE em padrão de relatório
  (negativos entre parênteses, resultado negativo em vermelho) com grupos recolhidos (+/− à esquerda, 1/2 no topo
  abre/fecha todos). Logo e botões são desenhados pelo Excel em `hoth/acabamento.py`.

## Gerar de novo a partir da planilha antiga

```powershell
.venv\Scripts\python.exe scripts\migrar_2026.py
```

A planilha antiga é copiada para uma pasta temporária e só lida de lá; o arquivo da rede nunca é alterado.
Se a planilha Hoth já existir, ela vai para `BKP\` antes de ser substituída. Precisa do Excel desktop para recalcular.

## Importar extratos (Fases 3 e 4)

Feche a planilha no Excel antes de gravar.

```powershell
.venv\Scripts\python.exe scripts\importar.py previa "C:\caminho\extrato Santander.xlsx"
.venv\Scripts\python.exe scripts\importar.py previa "C:\caminho\Extrato Cora.ofx"
```

1. **previa**: lê o extrato, separa o que já está na planilha e classifica os novos. Abre
   `Relatorios\Previa importacao.xlsx`. Na coluna **Conta (confirme ou corrija)**, verde = conta proposta e
   amarelo = para revisar (lista do Plano de Contas; em branco = entra como *Sem classificação*). Salve e feche.
2. **gravar**: `importar.py gravar` grava a prévia revisada na planilha em uso:
   - recusa se a planilha estiver aberta;
   - copia a versão atual para `BKP\` (guarda as últimas 60);
   - grava pelo próprio Excel numa cópia temporária, confere duplicados de novo e só então troca o arquivo;
   - registra na aba Auditoria (quantos lançamentos, de onde, e qual backup);
   - no OFX da Cora, grava o saldo do extrato em *Saldos Informados*.
   Se o extrato já estava todo na planilha, nada é alterado.
3. **backups** / **restaurar**: `importar.py backups` lista as versões; `importar.py restaurar "NOME DO ARQUIVO"` volta
   a planilha para aquela versão (a atual também vai para o BKP antes).

Os caminhos da planilha, do BKP e da pasta de comprovantes ficam em `hoth/config.py` e podem ser trocados num
arquivo `hoth.json` na raiz do projeto.

**Senha de abertura:** a planilha **não tem senha** desde 23/10/2026 (a senha impedia o Power BI de ler o arquivo;
foi removida com `scripts\remover_senha.py`). O app ainda abre uma planilha com senha se `senha_planilha` estiver no
`hoth.json`, e `scripts\aplicar_senha.py` voltaria a aplicá-la, mas isso quebra o Power BI.

**Regras fixas:** `Regras fixas.json`, ao lado da planilha, define a conta de fornecedores do RET pelo código
(`"00487": conta`) ou manda sempre revisar (conta vazia). Valem antes do aprendizado pelo histórico.

Documento completo do projeto: `DESENVOLVIMENTO.md`.

## Pacote e piloto (Fase 6)

```powershell
.venv\Scripts\python.exe scripts\empacotar.py --marcador "etapa"  # testes + telas + executável + instalador ZIP
.venv\Scripts\python.exe scripts\conferir_piloto.py --mes 10  # antiga x Hoth no mês
```

Roteiro do piloto: `Relatorios\Roteiro do Piloto.md`.
