"""Check that every repository-owned file is documented in PROJECT_MAP.md."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
result = subprocess.run(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    cwd=root, check=True, capture_output=True,
)
paths = {path for path in result.stdout.decode("utf-8").split("\0") if path}
document = (root / "PROJECT_MAP.md").read_text(encoding="utf-8")
missing = sorted(path for path in paths if (root / path).is_file() and f"`{path}`" not in document)
if missing:
    print("Missing from PROJECT_MAP.md:")
    print("\n".join(missing))
    raise SystemExit(1)
print(f"PROJECT_MAP.md covers all {len(paths)} repository files.")
