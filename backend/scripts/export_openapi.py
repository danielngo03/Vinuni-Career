from __future__ import annotations

import json
from pathlib import Path

from app.main import app


def main() -> None:
    destination = Path("contracts/openapi-v1.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI contract written to {destination}")


if __name__ == "__main__":
    main()
