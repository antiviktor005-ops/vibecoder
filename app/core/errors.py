class InputError(Exception):
    """A safe, user-facing application error."""


def safe_error(exc):
    orig = getattr(exc, "orig", exc)
    state = getattr(orig, "sqlstate", None)
    if not (isinstance(state, str) and len(state) == 5 and state.isascii() and state.isalnum()):
        return type(exc).__name__
    hints = {
        "42P01": "таблица отсутствует",
        "42703": "столбец отсутствует",
        "42501": "недостаточно прав",
        "3F000": "схема недоступна",
    }
    return f"{type(exc).__name__}, SQLSTATE {state} ({hints.get(state, 'ошибка PostgreSQL')})"
