import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


ROOT_DIR: Path = Path(__file__).resolve().parent.parent
ENV_FILE: Path = ROOT_DIR / ".env"


@dataclass(frozen=True)
class Settings:
    walmart_username: str = field(default="")
    walmart_password: str = field(default="")
    chromium_path: Optional[str] = field(default=None)
    headless: bool = field(default=False)
    login_url: str = field(
        default="https://retaillink.login.wal-mart.com/login"
    )
    user_data_dir: Optional[str] = field(default=None)

    @classmethod
    def from_env(cls, env_path: Path = ENV_FILE) -> "Settings":
        load_dotenv(dotenv_path=env_path)

        return cls(
            walmart_username=os.getenv("WALMART_USERNAME", ""),
            walmart_password=os.getenv("WALMART_PASSWORD", ""),
            chromium_path=os.getenv("CHROMIUM_PATH", None),
            headless=os.getenv("HEADLESS", "false").lower() == "true",
            login_url=os.getenv(
                "LOGIN_URL",
                "https://retaillink.login.wal-mart.com/login",
            ),
            user_data_dir=os.getenv("USER_DATA_DIR", None),
        )

    def validate(self) -> None:
        missing: list[str] = []
        if not self.walmart_username:
            missing.append("WALMART_USERNAME")
        if not self.walmart_password:
            missing.append("WALMART_PASSWORD")
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Ensure they are set in {ENV_FILE}"
            )


settings: Settings = Settings.from_env()
