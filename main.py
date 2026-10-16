"""Точка входа для сборки бинарника.

PyInstaller выполняет поданный ему файл как ``__main__`` без пакетного
окружения, поэтому относительные импорты внутри ``activity_renew/__main__.py``
там не работают. Этот файл — тонкая обёртка: он же годится и для обычного
запуска, ``python3 main.py``.
"""

from activity_renew.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
