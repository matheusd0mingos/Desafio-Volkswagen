"""Listas fechadas (dados de referência do domínio)."""
STATUS_FROTA = {"disponivel": "Disponível", "em manutencao": "Em manutenção", "indisponivel": "Indisponível"}
STATUS_OCORRENCIA = {"aberto": "Aberto", "em analise": "Em análise", "fechado": "Fechado", "concluido": "Fechado"}
STATUS_TESTE = {"planejado": "Planejado", "em andamento": "Em andamento", "concluido": "Concluído", "atrasado": "Atrasado"}
# Catálogo fechado de tipos de teste (o que existe hoje na base, já padronizado)
TIPOS_TESTE = ["ACC", "Conforto e vibração", "Consumo de combustível", "Durabilidade em pista", "Frenagem",
               "Subida em rampa", "Teste de eixo", "Teste térmico", "Validação CAN"]
NOME_TESTE = {"durabilidade - pista": "Durabilidade em pista", "teste de frenagem": "Frenagem"}
