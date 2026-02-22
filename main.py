import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from opentele.td import TDesktop
from opentele.tl import TelegramClient
from opentele.api import API, UseCurrentSession
from telethon import functions
from TGConvertor import SessionManager
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from InquirerPy import inquirer
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich import box


# -----------------------------------------------------------------------------
# Конфигурация
# -----------------------------------------------------------------------------

console = Console()

SESSIONS_DIR = "sessions"
TDATAS_DIR = "tdatas"
RESULTS_FILE = "conversion_results.json"


# -----------------------------------------------------------------------------
# Поиск файлов и определение типа
# -----------------------------------------------------------------------------

def detect_session_type(file_path: Path) -> str:
    if file_path.is_dir():
        if (file_path / "D877F783D5D3EF8C").exists() or (
            file_path / "key_datas"
        ).exists():
            return "tdata"
        return "unknown"
    if file_path.suffix == ".session":
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            if "sessions" in tables:
                return "telethon"
            return "pyrogram"
        except Exception:
            return "pyrogram"
    return "unknown"


def find_input_files() -> List[Tuple[Path, str]]:
    sessions_path = Path(SESSIONS_DIR)
    if not sessions_path.exists():
        console.print(f"[yellow]⚠ Папка {SESSIONS_DIR} не найдена[/yellow]")
        return []

    found = []
    for path in sessions_path.rglob("*"):
        if path.is_file() and path.suffix == ".session":
            session_type = detect_session_type(path)
            if session_type != "unknown":
                found.append((path, session_type))
        elif path.is_dir() and detect_session_type(path) == "tdata":
            found.append((path, "tdata"))

    return sorted(found, key=lambda x: str(x[0]))


# -----------------------------------------------------------------------------
# Информация об аккаунте
# -----------------------------------------------------------------------------

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


def get_output_session_name(account_info: Dict, prefix: str = "session") -> str:
    if account_info and account_info.get("username"):
        return f"{prefix}_{account_info['username']}.session"
    if account_info and account_info.get("user_id"):
        return f"{prefix}_{account_info['user_id']}.session"
    return f"{prefix}_unknown.session"


# -----------------------------------------------------------------------------
# Конвертация Telethon → tdata
# -----------------------------------------------------------------------------

async def convert_telethon_to_tdata(
    session_file: Path,
    progress: Progress,
    task_id,
) -> Dict:
    session_path = str(session_file.with_suffix(""))
    client = None
    result = {
        "input_file": str(session_file),
        "input_type": "telethon",
        "output_type": "tdata",
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
            description=f"[cyan]Telethon: подключение к {session_file.name}...[/cyan]",
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
            description=f"[cyan]Telethon: получение информации об аккаунте...[/cyan]",
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
            description=f"[cyan]Telethon: конвертация в tdata...[/cyan]",
        )
        tdesk = await client.ToTDesktop(flag=UseCurrentSession, api=api)
        out_folder.mkdir(parents=True, exist_ok=True)
        tdesk.SaveTData(str(out_folder))

        result["status"] = "success"
        progress.update(
            task_id,
            description=f"[green]✓ Telethon → tdata: {session_file.name}[/green]",
        )
        return result

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
        progress.update(
            task_id,
            description=f"[red]✗ Telethon: ошибка {session_file.name}[/red]",
        )
        return result
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


# -----------------------------------------------------------------------------
# Конвертация Pyrogram → tdata
# -----------------------------------------------------------------------------

async def convert_pyrogram_to_tdata(
    session_file: Path,
    progress: Progress,
    task_id,
) -> Dict:
    client = None
    result = {
        "input_file": str(session_file),
        "input_type": "pyrogram",
        "output_type": "tdata",
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
            description=f"[cyan]Pyrogram: загрузка {session_file.name}...[/cyan]",
        )

        temp_session_path = Path(
            session_file.parent / f"temp_{session_file.stem}.session"
        )
        session = await SessionManager.from_pyrogram_file(str(session_file))
        await session.to_telethon_file(str(temp_session_path))

        session_path = str(temp_session_path.with_suffix(""))

        progress.update(
            task_id,
            description=f"[cyan]Pyrogram: подключение...[/cyan]",
        )
        api = API.TelegramDesktop.Generate()
        client = TelegramClient(session_path, api=api)
        await client.connect()

        if not await client.is_user_authorized():
            result["error"] = "Сессия не авторизована"
            progress.update(
                task_id,
                description=f"[red]✗ Pyrogram: не авторизована[/red]",
            )
            return result

        progress.update(
            task_id,
            description=f"[cyan]Pyrogram: получение информации...[/cyan]",
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
            description=f"[cyan]Pyrogram: конвертация в tdata...[/cyan]",
        )
        tdesk = await client.ToTDesktop(flag=UseCurrentSession, api=api)
        out_folder.mkdir(parents=True, exist_ok=True)
        tdesk.SaveTData(str(out_folder))

        result["status"] = "success"
        progress.update(
            task_id,
            description=f"[green]✓ Pyrogram → tdata: {session_file.name}[/green]",
        )
        return result

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
        progress.update(
            task_id,
            description=f"[red]✗ Pyrogram: ошибка {session_file.name}[/red]",
        )
        return result
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        temp_session_path = Path(
            session_file.parent / f"temp_{session_file.stem}.session"
        )
        if temp_session_path.exists():
            try:
                temp_session_path.unlink()
            except Exception:
                pass


# -----------------------------------------------------------------------------
# Конвертация tdata → Telethon session
# -----------------------------------------------------------------------------

async def convert_tdata_to_telethon(
    tdata_folder: Path,
    progress: Progress,
    task_id,
) -> Dict:
    client = None
    result = {
        "input_file": str(tdata_folder),
        "input_type": "tdata",
        "output_type": "telethon",
        "session_name": tdata_folder.name,
        "status": "error",
        "account_info": None,
        "output_file": None,
        "error": None,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        progress.update(
            task_id,
            description=f"[cyan]tdata: загрузка {tdata_folder.name}...[/cyan]",
        )

        tdesk = TDesktop(str(tdata_folder))
        if not tdesk.isLoaded():
            result["error"] = "Не удалось загрузить tdata"
            progress.update(
                task_id,
                description=f"[red]✗ tdata: не загружен[/red]",
            )
            return result

        progress.update(
            task_id,
            description=f"[cyan]tdata: конвертация в Telethon...[/cyan]",
        )

        temp_session_name = f"temp_{tdata_folder.name}.session"
        temp_session_path = Path(temp_session_name)
        api = API.TelegramDesktop.Generate()
        client = await tdesk.ToTelethon(
            session=str(temp_session_path.with_suffix("")),
            flag=UseCurrentSession,
            api=api,
        )
        await client.connect()

        if not await client.is_user_authorized():
            result["error"] = "Сессия не авторизована"
            progress.update(
                task_id,
                description=f"[red]✗ tdata: не авторизована[/red]",
            )
            return result

        progress.update(
            task_id,
            description=f"[cyan]tdata: получение информации...[/cyan]",
        )
        account_info = await get_account_info(client)
        if not account_info:
            result["error"] = "Не удалось получить информацию об аккаунте"
            return result

        session_name = get_output_session_name(account_info, "session")
        output_file = Path(SESSIONS_DIR) / session_name
        Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

        if temp_session_path.exists():
            temp_session_path.rename(output_file)

        result["account_info"] = account_info
        result["output_file"] = str(output_file)

        result["status"] = "success"
        progress.update(
            task_id,
            description=f"[green]✓ tdata → Telethon: {tdata_folder.name}[/green]",
        )
        return result

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
        progress.update(
            task_id,
            description=f"[red]✗ tdata: ошибка {tdata_folder.name}[/red]",
        )
        return result
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        temp_session_path = Path(f"temp_{tdata_folder.name}.session")
        if temp_session_path.exists() and result.get("status") != "success":
            try:
                temp_session_path.unlink()
            except Exception:
                pass


# -----------------------------------------------------------------------------
# Вывод результатов
# -----------------------------------------------------------------------------

def print_account_table(results: List[Dict]) -> None:
    table = Table(
        title="📊 Результаты конвертации",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("№", style="cyan", width=4, justify="center")
    table.add_column("Тип", style="yellow", width=12)
    table.add_column("Имя", style="green", width=25)
    table.add_column("Username", style="yellow", width=20)
    table.add_column("Телефон", style="blue", width=15)
    table.add_column("User ID", style="cyan", width=12)
    table.add_column("Чаты", style="magenta", width=8, justify="center")
    table.add_column("Контакты", style="magenta", width=10, justify="center")
    table.add_column("Статус", style="bold", width=12, justify="center")
    table.add_column("Результат", style="dim", width=30)

    for idx, result in enumerate(results, 1):
        conversion_type = f"{result.get('input_type', '?')} → {result.get('output_type', '?')}"
        if result["status"] == "success" and result["account_info"]:
            info = result["account_info"]
            status_style = "[green]✓ Успешно[/green]"
            name = info["name"]
            username = info["username_display"]
            phone = info["phone"]
            user_id = str(info["user_id"])
            chats = str(info["chats_count"])
            contacts = str(info["contacts_count"])
            if result.get("output_folder"):
                output = Path(result["output_folder"]).name
            elif result.get("output_file"):
                output = Path(result["output_file"]).name
            else:
                output = "-"
        elif result["status"] == "skipped":
            status_style = "[yellow]⊘ Пропущено[/yellow]"
            name = Path(result["input_file"]).stem
            username = "-"
            phone = "-"
            user_id = "-"
            chats = "-"
            contacts = "-"
            output = "-"
            if result.get("error"):
                name = (
                    f"{name}\n[dim yellow]{result['error'][:30]}...[/dim yellow]"
                )
        else:
            status_style = "[red]✗ Ошибка[/red]"
            name = Path(result["input_file"]).stem
            username = "-"
            phone = "-"
            user_id = "-"
            chats = "-"
            contacts = "-"
            output = "-"
            if result.get("error"):
                name = (
                    f"{name}\n[dim red]{result['error'][:30]}...[/dim red]"
                )
        table.add_row(
            str(idx),
            conversion_type,
            name,
            username,
            phone,
            user_id,
            chats,
            contacts,
            status_style,
            output,
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


# -----------------------------------------------------------------------------
# Меню и выбор режима
# -----------------------------------------------------------------------------

def show_menu() -> str:
    console.print("\n")
    console.print(
        Panel.fit(
            "[bold cyan]📋 Меню конвертации[/bold cyan]\n"
            "[dim]↑↓ — навигация, Enter — выбор[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    choice = inquirer.select(
        message="Выберите действие:",
        choices=[
            {"name": "Telethon → tdata — конвертировать Telethon сессии в tdata", "value": "1"},
            {"name": "Pyrogram → tdata — конвертировать Pyrogram сессии в tdata", "value": "2"},
            {"name": "tdata → Telethon — конвертировать tdata папки в Telethon сессии", "value": "3"},
            {"name": "Автообработка — автоматически определить тип и конвертировать всё", "value": "4"},
            {"name": "Выход", "value": "5"},
        ],
        default="4",
        pointer="▶",
    ).execute()

    return choice


def filter_files_by_type(
    input_files: List[Tuple[Path, str]], file_type: str
) -> List[Tuple[Path, str]]:
    return [(path, ftype) for path, ftype in input_files if ftype == file_type]


async def process_conversion(
    input_files: List[Tuple[Path, str]], mode: str
) -> List[Dict]:
    results = []
    Path(TDATAS_DIR).mkdir(parents=True, exist_ok=True)
    Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        tasks = []
        for file_path, file_type in input_files:
            task_id = progress.add_task("[cyan]Ожидание...", total=1)
            tasks.append((file_path, file_type, task_id))

        for file_path, file_type, task_id in tasks:
            if mode == "auto" or (
                mode == "telethon" and file_type == "telethon"
            ):
                if file_type == "telethon":
                    result = await convert_telethon_to_tdata(
                        file_path, progress, task_id
                    )
                elif file_type == "pyrogram":
                    result = await convert_pyrogram_to_tdata(
                        file_path, progress, task_id
                    )
                elif file_type == "tdata":
                    result = await convert_tdata_to_telethon(
                        file_path, progress, task_id
                    )
                else:
                    result = {
                        "input_file": str(file_path),
                        "input_type": "unknown",
                        "output_type": "unknown",
                        "status": "error",
                        "error": "Неизвестный тип файла",
                        "timestamp": datetime.now().isoformat(),
                    }
            elif mode == "telethon" and file_type != "telethon":
                result = {
                    "input_file": str(file_path),
                    "input_type": file_type,
                    "output_type": "tdata",
                    "status": "skipped",
                    "error": "Пропущено (не Telethon)",
                    "timestamp": datetime.now().isoformat(),
                }
            elif mode == "pyrogram" and file_type != "pyrogram":
                result = {
                    "input_file": str(file_path),
                    "input_type": file_type,
                    "output_type": "tdata",
                    "status": "skipped",
                    "error": "Пропущено (не Pyrogram)",
                    "timestamp": datetime.now().isoformat(),
                }
            elif mode == "tdata" and file_type != "tdata":
                result = {
                    "input_file": str(file_path),
                    "input_type": file_type,
                    "output_type": "telethon",
                    "status": "skipped",
                    "error": "Пропущено (не tdata)",
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                result = {
                    "input_file": str(file_path),
                    "input_type": file_type,
                    "output_type": "unknown",
                    "status": "error",
                    "error": "Неизвестный режим",
                    "timestamp": datetime.now().isoformat(),
                }
            results.append(result)
            progress.update(task_id, completed=1)

    return results


# -----------------------------------------------------------------------------
# Точка входа
# -----------------------------------------------------------------------------

async def run_conversion_cycle(
    input_files: List[Tuple[Path, str]], mode: str
) -> List[Dict]:
    return await process_conversion(input_files, mode)


def main() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]🔄 Конвертер Telegram Sessions[/bold cyan]\n"
            "[dim]Поддержка: Telethon ↔ tdata, Pyrogram → tdata[/dim]",
            border_style="cyan",
        )
    )

    while True:
        choice = show_menu()

        if choice == "5":
            console.print("\n[yellow]👋 До свидания![/yellow]\n")
            break

        input_files = find_input_files()
        if not input_files:
            console.print(
                f"\n[yellow]⚠ Нет файлов в папке {SESSIONS_DIR}[/yellow]\n"
            )
            if not Confirm.ask("[cyan]Продолжить?[/cyan]", default=True):
                break
            continue

        Path(TDATAS_DIR).mkdir(parents=True, exist_ok=True)
        Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

        mode_map = {
            "1": ("telethon", "Telethon → tdata"),
            "2": ("pyrogram", "Pyrogram → tdata"),
            "3": ("tdata", "tdata → Telethon"),
            "4": ("auto", "Автообработка"),
        }

        mode, mode_name = mode_map[choice]

        if mode != "auto":
            filtered_files = filter_files_by_type(input_files, mode)
            if not filtered_files:
                console.print(
                    f"\n[yellow]⚠ Не найдено файлов типа '{mode}'[/yellow]\n"
                )
                continue
            input_files = filtered_files

        console.print(
            f"\n[cyan]📁 Найдено файлов: {len(input_files)}[/cyan]"
        )
        console.print(f"[cyan]Режим: {mode_name}[/cyan]\n")

        results = asyncio.run(run_conversion_cycle(input_files, mode))

        print_account_table(results)
        save_results_to_json(results)

        successful = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "error")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        console.print(
            f"\n[bold]📈 Итого:[/bold] "
            f"[green]✓ {successful} успешно[/green] | "
            f"[red]✗ {failed} ошибок[/red]",
            end="",
        )
        if skipped > 0:
            console.print(f" | [yellow]⊘ {skipped} пропущено[/yellow]")
        else:
            console.print()

        console.print()
        if not Confirm.ask("[cyan]Выполнить ещё одну операцию?[/cyan]", default=True):
            break


if __name__ == "__main__":
    main()
