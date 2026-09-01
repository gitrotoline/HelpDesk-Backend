# HD-31: mapeamento nome -> grau usado pela migration de dados 0007 (backfill
# de `TicketPriority.level` para bases existentes). Fica num módulo próprio
# (em vez de dentro do arquivo de migration) porque migrations não são
# módulos Python "normais" pra importar em teste (nome começa com dígito).
#
# Conveniência para bases existentes, NÃO regra de negócio: só reconhece os
# nomes mais comuns e deixa 0 (não reconhecido) para qualquer outro — não
# inventa grau para nome fora da lista.
KNOWN_LEVELS = {
    "baixa": 10,
    "media": 20,
    "alta": 30,
    "urgente": 40,
    "critica": 40,
}


def normalize(name):
    """Remove acentos e normaliza caixa/espaços para casar com KNOWN_LEVELS."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_name = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_name.strip().lower()


def level_for_name(name):
    """Retorna o grau conhecido para o nome (normalizado), ou 0 se não reconhecer."""
    return KNOWN_LEVELS.get(normalize(name), 0)
