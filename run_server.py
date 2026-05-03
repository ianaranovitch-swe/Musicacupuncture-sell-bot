"""Обёртка: локально можно по-прежнему ``python run_server.py``."""

from music_sales.web_entry import app, main

if __name__ == "__main__":
    main()
