# Session to TData

Converts Telegram .session (Telethon) to tdata for Telegram Desktop. Batch processing, collects account info (name, username, phone, chats and contacts count).

## Requirements

- Python 3.12 (opentele does not work with 3.14)

## Install

```bash
git clone https://github.com/ishaks1234asadsgfdsg/telethon-session-to-tdata
cd session_to_tdata
python3.12 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

1. Put .session files in the `sessions/` folder (subfolders allowed).
2. Run:

```bash
source venv/bin/activate
python main.py
```

3. Output:
   - tdata folders in `tdatas/` (names: `tdata_username` or `tdata_user_id`);
   - report in console;
   - `conversion_results.json` with full report.

## Structure

- `sessions/` ? source .session files
- `tdatas/` ? converted tdata folders
- `conversion_results.json` ? results in JSON
