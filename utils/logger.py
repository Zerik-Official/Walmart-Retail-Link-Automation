import threading
from enum import StrEnum, unique
from typing import Literal, Final, Set, Dict
from datetime import datetime
from colorama import Fore, Style, init as colorama_init


colorama_init(autoreset=True)

_log_lock = threading.Lock()
ENABLED_TAGS: Final[Set[str]] = set()
DISABLED_LEVELS: Final[Set[str]] = set()
TAG_LEVEL_RULES: Dict[str, Set[str]] = {
    "LOADER": {"DEBUG"},
    "WINDOW_CONTROLLER": {"DEBUG"},
    "PX": {"DEBUG"},
}

LogLevel = Literal["INFO", "SUCCESS", "WARNING", "ERROR", "DEBUG", "CRITICAL"]


@unique
class Tags(StrEnum):
    MAIN = "MAIN"
    BROWSER = "BROWSER"
    PX = "PX"
    MFA = "MFA"
    LOGIN = "LOGIN"
    LASTPASS = "LASTPASS"
    SYSTEM = "SYSTEM"


def log(level: LogLevel, tag: Tags | str, message: str) -> None:
    level_up: str = level.upper()
    tag_up: str = tag.upper() if isinstance(tag, str) else tag.value

    if level_up in DISABLED_LEVELS:
        return
    if ENABLED_TAGS and tag_up not in ENABLED_TAGS:
        return
    if tag_up in TAG_LEVEL_RULES and level_up in TAG_LEVEL_RULES[tag_up]:
        return

    timestamp: str = datetime.now().strftime("%H:%M:%S")

    colors: Final[Dict[str, str]] = {
        "INFO": Fore.CYAN,
        "SUCCESS": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "DEBUG": Fore.MAGENTA,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    color: str = colors.get(level_up, Fore.WHITE)
    lvl_fmt: str = f"{level_up:^9}"
    tag_fmt: str = f"{tag_up:^20}"

    with _log_lock:
        print(
            f"{Style.DIM}{timestamp}{Style.RESET_ALL} "
            f"[{color}{lvl_fmt}{Style.RESET_ALL}] "
            f"[{Fore.WHITE}{Style.BRIGHT}{tag_fmt}{Style.RESET_ALL}] "
            f"{message}"
        )
