"""Apply migrations before a release. Keep connection details out of logs."""

import logging
import time

from alembic.config import Config

from alembic import command


def main():
    for attempt in range(5):
        try:
            command.upgrade(Config("alembic.ini"), "head")
            print("Схема БД обновлена.", flush=True)
            return
        except Exception as exc:
            logging.error("Миграция, попытка %d: %s", attempt + 1, type(exc).__name__)
            if attempt == 4:
                raise SystemExit(1) from None
            time.sleep(2**attempt)


if __name__ == "__main__":
    main()
