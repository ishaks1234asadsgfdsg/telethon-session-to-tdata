# Session → TData

Конвертирует Telegram .session (Telethon) в tdata для Telegram Desktop. Массовая обработка, сбор данных об аккаунте (имя, username, телефон, кол-во чатов и контактов).

## Требования

- Python 3.12 (opentele не работает с 3.14)

## Установка

```bash
git clone https://github.com/ishaks1234asadsgfdsg/telethon-session-to-tdata
cd telethon-session-to-tdata
python3.12 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Использование

1. Положите .session файлы в папку `sessions/` (можно в подпапки).
2. Запустите:

```bash
source venv/bin/activate
python main.py
```

3. Результаты:
   - папки tdata в `tdatas/` (имена: `tdata_username` или `tdata_user_id`);
   - отчёт в консоли;
   - `conversion_results.json` с полным отчётом.

## Структура

- `sessions/` — исходные .session файлы
- `tdatas/` — сконвертированные папки tdata
- `conversion_results.json` — результаты в JSON
