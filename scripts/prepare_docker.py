"""Generate local container secrets without echoing them or copying provider credentials."""

import secrets
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
path = root / ".env.docker"
values = dict(dotenv_values(path)) if path.exists() else {}
values.setdefault("POSTGRES_PASSWORD", secrets.token_hex(24))
values.setdefault("APP_AUTH_TOKEN", secrets.token_hex(24))
local = dotenv_values(root / ".env.local")
if local.get("SEC_USER_AGENT"):
    values.setdefault("SEC_USER_AGENT", local["SEC_USER_AGENT"])
path.write_text("".join(f'{key}="{value}"\n' for key, value in values.items()), encoding="utf-8")
print("Docker secrets prepared in .env.docker. No credentials were printed.")
