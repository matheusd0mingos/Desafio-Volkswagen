import unicodedata


def sem_acento(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s))
                   if unicodedata.category(c) != "Mn").lower().strip()


def vazio(v) -> bool:
    return v is None or (isinstance(v, float) and v != v)
