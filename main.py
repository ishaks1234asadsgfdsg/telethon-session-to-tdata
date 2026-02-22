import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from opentele.tl import TelegramClient
from opentele.api import API, UseCurrentSession
from telethon import functions
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich import box


console = Console()

SESSIONS_DIR = "sessions"
TDATAS_DIR = "tdatas"
RESULTS_FILE = "conversion_results.json"


def find_session_files() -> List[Path]:
    sessions_path = Path(SESSIONS_DIR)
    if not sessions_path.exists():
        console.print(f"[yellow]⚠ Папка {SESSIONS_DIR} не найдена[/yellow]")
        return []

    found = []
    for path in sessions_path.rglob("*.session"):
        if path.is_file():
            found.append(path)
    return sorted(found)


async def get_account_info(client) -> Optional[Dict]:
    try:
        me = await client.get_me()

        first_name = me.first_name or ""
        last_name = me.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or "Не указано"
        username_raw = me.username or None
        username = f"@{username_raw}" if username_raw else None
        phone = me.phone or None
        user_id = me.id

        dialogs = await client.get_dialogs()
        chats_count = len(dialogs)

        try:
            contacts_result = await client(
                functions.contacts.GetContactsRequest(hash=0)
            )
            if hasattr(contacts_result, "contacts"):
                contacts_count = len(contacts_result.contacts)
            else:
                contacts_count = 0
        except Exception:
            contacts_count = 0

        return {
            "name": full_name,
            "username": username_raw,
            "username_display": username or "Не указан",
            "phone": phone or "Не указан",
            "user_id": user_id,
            "chats_count": chats_count,
            "contacts_count": contacts_count,
        }
    except Exception as e:
        console.print(
            f"[red]✗ Не удалось получить информацию об аккаунте: {e}[/red]"
        )
        return None


def get_output_folder_name(account_info: Dict) -> str:
    if account_info and account_info.get("username"):
        return f"tdata_{account_info['username']}"
    if account_info and account_info.get("user_id"):
        return f"tdata_{account_info['user_id']}"
    return "tdata_unknown"


async def convert_session_to_tdata(
    session_file: Path,
    progress: Progress,
    task_id,
) -> Dict:
    session_path = str(session_file.with_suffix(""))
    client = None
    result = {
        "session_file": str(session_file),
        "session_name": session_file.name,
        "status": "error",
        "account_info": None,
        "output_folder": None,
        "error": None,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        progress.update(
            task_id,
            description=f"[cyan]Подключение к {session_file.name}...[/cyan]",
        )
        api = API.TelegramDesktop.Generate()
        client = TelegramClient(session_path, api=api)
        await client.connect()

        if not await client.is_user_authorized():
            result["error"] = "Сессия не авторизована"
            progress.update(
                task_id,
                description=f"[red]✗ {session_file.name} - не авторизована[/red]",
            )
            return result

        progress.update(
            task_id,
            description=f"[cyan]Получение информации об аккаунте {session_file.name}...[/cyan]",
        )
        account_info = await get_account_info(client)
        if not account_info:
            result["error"] = "Не удалось получить информацию об аккаунте"
            return result

        folder_name = get_output_folder_name(account_info)
        out_folder = Path(TDATAS_DIR) / folder_name
        result["account_info"] = account_info
        result["output_folder"] = str(out_folder)

        progress.update(
            task_id,
            description=f"[cyan]Конвертация {session_file.name} в tdata...[/cyan]",
        )
        tdesk = await client.ToTDesktop(flag=UseCurrentSession, api=api)
        out_folder.mkdir(parents=True, exist_ok=True)
        tdesk.SaveTData(str(out_folder))

        result["status"] = "success"
        progress.update(
            task_id,
            description=f"[green]✓ {session_file.name} - готово[/green]",
        )
        return result

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
        progress.update(
            task_id,
            description=f"[red]✗ {session_file.name} - ошибка[/red]",
        )
        return result
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


def print_account_table(results: List[Dict]) -> None:
    table = Table(
        title="📊 Результаты конвертации",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("№", style="cyan", width=4, justify="center")
    table.add_column("Имя", style="green", width=25)
    table.add_column("Username", style="yellow", width=20)
    table.add_column("Телефон", style="blue", width=15)
    table.add_column("User ID", style="cyan", width=12)
    table.add_column("Чаты", style="magenta", width=8, justify="center")
    table.add_column("Контакты", style="magenta", width=10, justify="center")
    table.add_column("Статус", style="bold", width=12, justify="center")
    table.add_column("Папка", style="dim", width=30)

    for idx, result in enumerate(results, 1):
        if result["status"] == "success" and result["account_info"]:
            info = result["account_info"]
            status_style = "[green]✓ Успешно[/green]"
            name = info["name"]
            username = info["username_display"]
            phone = info["phone"]
            user_id = str(info["user_id"])
            chats = str(info["chats_count"])
            contacts = str(info["contacts_count"])
            folder = Path(result["output_folder"]).name
        else:
            status_style = "[red]✗ Ошибка[/red]"
            name = Path(result["session_file"]).stem
            username = "-"
            phone = "-"
            user_id = "-"
            chats = "-"
            contacts = "-"
            folder = "-"
            if result.get("error"):
                name = (
                    f"{name}\n[dim red]{result['error'][:30]}...[/dim red]"
                )
        table.add_row(
            str(idx),
            name,
            username,
            phone,
            user_id,
            chats,
            contacts,
            status_style,
            folder,
        )

    console.print("\n")
    console.print(table)


def save_results_to_json(results: List[Dict]) -> None:
    output = {
        "conversion_date": datetime.now().isoformat(),
        "total_sessions": len(results),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
    results_path = Path(RESULTS_FILE)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    console.print(f"\n[green]✓ Результаты сохранены в {RESULTS_FILE}[/green]")


async def main() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]🔄 Конвертер Telegram Session → TData[/bold cyan]\n"
            "[dim]Массовая обработка сессий с получением информации об аккаунтах[/dim]",
            border_style="cyan",
        )
    )

    session_files = find_session_files()
    if not session_files:
        console.print(
            f"[yellow]⚠ Нет .session файлов в папке {SESSIONS_DIR}[/yellow]"
        )
        return

    Path(TDATAS_DIR).mkdir(parents=True, exist_ok=True)
    console.print(f"\n[cyan]📁 Найдено сессий: {len(session_files)}[/cyan]\n")

    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        tasks = []
        for session_file in session_files:
            task_id = progress.add_task("[cyan]Ожидание...", total=1)
            tasks.append((session_file, task_id))

        for session_file, task_id in tasks:
            result = await convert_session_to_tdata(
                session_file, progress, task_id
            )
            results.append(result)
            progress.update(task_id, completed=1)

    print_account_table(results)
    save_results_to_json(results)

    successful = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    console.print(
        f"\n[bold]📈 Итого:[/bold] "
        f"[green]✓ {successful} успешно[/green] | "
        f"[red]✗ {failed} ошибок[/red]\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
