"""Create a local .env with random secrets without replacing existing settings."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("REPLACE_WITH_RANDOM_SECRET", secrets.token_urlsafe(64))
content = content.replace("REPLACE_WITH_RANDOM_PASSWORD", secrets.token_urlsafe(32))
try:
    with (root / ".env").open("x", encoding="utf-8") as target:
        target.write(content)
except FileExistsError:
    print(".env already exists; left unchanged.")
else:
    print(".env created. Keep it private.")
