# Tratamento dos dados de validação — arquitetura hexagonal

```
src/validacao/
├── dominio/        ← regras de negócio puras (sem pandas, sem I/O)
│   ├── modelos.py        entidades, Achado, Config
│   ├── normalizadores.py ID, data, status, pessoa, catálogo
│   ├── regras.py         1 regra = 1 classe (Strategy)
│   └── servicos.py       validador de km, duplicatas, status calculado
├── aplicacao/
│   ├── portas.py         FonteDadosBrutos, RepositorioResultado (Protocol)
│   └── tratar_base.py    caso de uso: orquestra domínio + portas
├── adaptadores/
│   └── excel.py          único arquivo que conhece pandas
└── __main__.py           raiz de composição (liga adaptador ↔ porta)
tests/                    separado; usa adaptadores em memória
```

Rodar: `PYTHONPATH=src python -m validacao Case_Dados_Validacao_.xlsx saida.xlsx`
Testar: `pip install -e .[dev] && pytest` (o teste de integração roda se o Excel estiver na raiz)

Trocar Excel por SharePoint = escrever `adaptadores/sharepoint.py` com `ler()` e `salvar()`. Domínio e testes não mudam.

## Tratamento de dados em Python, passo a passo (versão macaqueada)

> 🧺 **Analogia: uma lavanderia.** Recebe a roupa, separa e etiqueta, confere peça por peça, compara os pares,
> junta o que veio repetido, conta o que ficou pronto e devolve ao dono o que tem mancha que ela não sabe tirar.

**3 regras de ouro** (mnemônico **P-P-N**):
1. **P**adroniza sozinho o que é seguro (formato de ID, data, status, nome).
2. **P**ergunta ao dono o que muda o sentido do dado (km suspeito, duplicata, status "?").
3. **N**unca apaga: todo achado guarda a aba e a linha de origem do Excel.

```
 Excel bruto (4 abas, 79 linhas)
   │
   ① LER ............ ExcelFonte.ler()                    nada muda; só vira Python
   ② PADRONIZAR ..... dominio/normalizadores.py           42 correções automáticas + 4 alertas
   ③ CONFERIR LINHA . dominio/regras.py                   14 achados
   ④ COMPARAR LINHAS  servicos.ValidadorLeituras          5 leituras em quarentena + 11 veículos atrasados
   ⑤ AGRUPAR ........ servicos.AnalisadorOcorrencias      3 duplicatas + 1 falha sistêmica
   ⑥ CALCULAR ....... status do teste, km, falhas únicas  9 / 11 / 16 → 12 falhas
   ⑦ GRAVAR ......... Excel tratado + SQLite              o que não entra vira pendência com dono
                                                          ───────────────
                                                          80 achados no log
```

### ① Ler · `adaptadores/excel.py`
Lê as 4 abas com pandas e entrega **linhas Python puras** para o domínio: célula vazia vira `None`, data do Excel
vira `datetime`. É o **único** lugar que conhece pandas; daqui para dentro, o código não sabe que existe Excel.

### ② Padronizar · `dominio/normalizadores.py`
Cada normalizador recebe um valor e devolve **valor padronizado + achados** (função pura, sem gravar nada).

| O quê | Como | Antes → depois | Casos |
|---|---|---|---|
| ID do veículo | Pega o número com regex e formata `PT-NN` | `PT 07`, `pt07`, `Protótipo 7` → `PT-07` | 4 |
| Data | Data do Excel passa direto; texto `aaaa-mm-dd` é ISO; texto `xx/yy/aaaa`: se `yy > 12`, só pode ser americano | `09/03/2026` → 2026-03-09 · `03/18/2026` → 2026-03-18 ⚠️ | 17 |
| Status | Tira acento, põe em minúscula e procura no catálogo | `ABERTO`, `aberto` → `Aberto` · `Concluído` → `Fechado` · `?` → `Indefinido` ⚠️ | 9 |
| Pessoa | Compara sobrenome + inicial com os nomes completos do plano | `marcos s.`, `M. Silva` → `Marcos Silva` | 11 |
| Tipo de teste | Catálogo de variantes | `Durabilidade - pista` → `Durabilidade em pista` | 2 |
| ID da ocorrência | Formata `OC-NNNN`; vazio vira provisório; repetido ganha `-B` | `OC-117` → `OC-0117` · vazio → `OC-SEMID-15` ⚠️ · 2º `106` → `OC-0106-B` ⚠️ | 3 |

⚠️ = corrigido, mas também vai para o dono confirmar.

### ③ Conferir cada linha · `dominio/regras.py`
Uma regra = uma classe pequena. Cada uma olha **uma linha só** e devolve achados.

| Regra | Exemplo real | Casos |
|---|---|---|
| Veículo existe na Frota? | PT-13, PT-14, PT-15 não existem | 3 |
| Fechamento ≥ abertura? | OC-0107: fechou 03/03, abriu 07/03 | 1 |
| Indisponível tem motivo? | PT-03, PT-08, PT-11 | 3 |
| Status do teste bate com as datas? | T-014 "Concluído" sem data; T-003 vencido e "Planejado" | 7 |

### ④ Comparar leituras de km · `servicos.ValidadorLeituras` ⭐ (a parte mais perguntada)
1. Ordena as leituras **por veículo e por data**.
2. Compara cada leitura com a **última leitura BOA** daquele veículo (não com a anterior qualquer).
3. Aplica 4 regras **nesta ordem**; a primeira que disparar põe a leitura em quarentena:

| Ordem | Regra | Conta | Caso real |
|---|---|---|---|
| 1 | Mesma data | data igual à da última boa | PT-02 em 09/03: 8.760 e 8.940 |
| 2 | Unidade errada | km atual ÷ anterior < 0,01 | PT-05: 16,62 depois de 16.010 → sugere 16.620 |
| 3 | Km regrediu | km atual < anterior | PT-07: 18.450 → 18.120 |
| 4 | Salto | aumento > 3.000 × nº de semanas; se a razão > 5, sugere ÷10 | PT-04: +188.030 em 1 semana → sugere 20.890 |

Fora isso: km vazio (PT-08) e veículo fora da Frota (PT-15) também vão para quarentena.

**Por que "última leitura BOA"? O caso PT-07:**

| Data | Km | Compara com | Resultado |
|---|---|---|---|
| 03/03 | 18.450 | — | ✅ OK (primeira) |
| 10/03 | 18.120 | 18.450 | 🚧 regrediu → quarentena |
| 17/03 | 21.900 | **18.450** (pula a ruim) | ✅ +3.450 em 2 semanas = 1.725/semana < 3.000 |
| 24/03 | 22.480 | 21.900 | ✅ |
| 31/03 | 23.000 | 22.480 | ✅ |

Se comparasse com 18.120, todo o resto do PT-07 viraria suspeito por causa de **um** erro. Na primeira versão,
o limite não considerava o intervalo entre leituras e marcava 21.900 como salto; o teste
`test_salto_considera_intervalo_entre_leituras` protege essa correção.

Por fim, veículo **sem leitura boa há mais de 7 dias** (contando da data mais recente, 31/03) entra no log: 11 de 12.

### ⑤ Agrupar duplicatas · `servicos.AnalisadorOcorrencias`
Compara as **palavras** das descrições (sem acento e sem "no", "de", "da"…) pela similaridade de Jaccard:
`palavras em comum ÷ palavras no total`.

| Par | Palavras | Similaridade | Resultado |
|---|---|---|---|
| OC-0104 × OC-0115 (PT-05) | iguais | 1,0 | duplicata (≥ 0,5, mesmo veículo) |
| OC-0106 × OC-0106-B (PT-07) | {vazamento, eixo} × {vazamento, eixo, traseiro} | 2 ÷ 3 = 0,67 | duplicata |
| OC-0108 × OC-0109 (PT-09) | {falha, can, intermitente} × {falha, comunicação, can} | 2 ÷ 4 = 0,5 | duplicata |
| OC-0108 (PT-09) × OC-0113 (PT-07) | iguais | 1,0 | ⚠️ **falha sistêmica** (≥ 0,6, veículos diferentes) |

A duplicata não é apagada: ganha o mesmo `grupo_duplicata` e o dono confirma.

### ⑥ Calcular · o funil das falhas abertas

| Passo | Falhas | Saíram | Por quê |
|---|---|---|---|
| Tudo que não está fechado (planilha crua) | 16 | | |
| − grupo já fechado | 15 | OC-0104 | a duplicata OC-0115 já fechou a mesma trinca |
| − veículo fora da Frota | 14 | OC-0114 | PT-13 não existe no cadastro |
| − duplicatas contam uma vez | **12** | OC-0106-B, OC-0109 | mesma falha do grupo OC-0106 e OC-0108 |

Das 12, duas têm status "?" e estão em quarentena até o dono informar.

O status do teste também é **calculado**: tem data realizada → Concluído; prevista antes do corte → Atrasado.

### ⑦ Gravar · `adaptadores/sqlite/repositorio.py`
Grava o Excel tratado e a base SQLite. O banco aplica as constraints; **o que ele recusa (8 linhas) e o que o
domínio pôs em quarentena (6) viram pendência com o nome do dono**, que resolve pela plataforma.

| Resumo em números | |
|---|---|
| Linhas no Excel | 79 |
| Linhas com algum problema | 41 (52%) |
| Achados no log | 80 (42 corrigidos sozinhos · 38 para o dono ou informativos) |
| Falhas abertas | 9, 11 ou 16 → **12** |
| Km rodado | 183.767 → **11.730** |

## Docker

```
dados/entrada/Case_Dados_Validacao_.xlsx   ← coloque o Excel aqui
make build && make test && make run        → dados/saida/Case_Dados_Tratados.xlsx
```

| Estágio | Para quê |
|---|---|
| `builder` | gera wheels do projeto + dependências |
| `teste` | instala o **pacote** e roda pytest (testa o que vai para produção) |
| `runtime` | imagem enxuta, sem testes, usuário não-root, entrada read-only |

Sem make: `docker compose run --rm testes` e `docker compose run --rm tratar`.

## Painel interativo (Streamlit)

```powershell
docker compose up --build -d painel     # abre em http://localhost:8501
docker compose logs -f painel           # ver logs
docker compose down                     # desligar
```
Sem Docker: `pip install -e .[painel]` e depois `validacao-painel`.
O painel é um adaptador primário: chama o mesmo caso de uso, sem duplicar regra.

## Base única em SQLite

`validacao entrada.xlsx saida.xlsx validacao.db` grava Excel **e** SQLite (Composite).
- `src/validacao/adaptadores/sqlite/schema.sql`: o modelo de dados (1.2) com as regras de entrada (1.3) como CONSTRAINTs nomeadas.
- `pendencia`: o que foi barrado, e por quem (domínio ou banco).
- `vw_gate_programa`: o Gate Review em uma consulta SQL.

## Plataforma (fluxo desejado funcionando)

1. **Carga inicial:** na primeira vez, o Excel de `dados/entrada/` é tratado e vira `dados/base/validacao.db`.
2. **Operação:** os engenheiros lançam km, ocorrências, status da frota e testes pela plataforma.
   Cada lançamento passa pelo domínio (regras entre linhas) e pelo banco (constraints).
3. **Pendências:** o que a carga inicial barrou fica com o dono, que aceita a sugestão, corrige ou descarta.
4. **Gate ao vivo:** lê a base única; muda no instante em que alguém lança.

`docker compose up --build -d painel` → http://localhost:8501 · "Reiniciar base" no Gate ao vivo refaz a carga.
