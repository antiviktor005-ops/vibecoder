"""Apply migrations before a release. Keep connection details out of logs."""

import logging
import time

from alembic.config import Config

from alembic import command
from app.core.errors import safe_error


def main():
    for attempt in range(5):
        try:
            command.upgrade(Config("alembic.ini"), "head")
            print("Схема БД обновлена.", flush=True)
            return
        except Exception as exc:
            logging.error("Миграция, попытка %d: %s", attempt + 1, safe_error(exc))
            if attempt == 4:
                raise SystemExit(1) from None
            time.sleep(2**attempt)


if __name__ == "__main__":
    main()
