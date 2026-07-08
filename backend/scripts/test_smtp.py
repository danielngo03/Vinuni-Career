"""Quick SMTP smoke test — sends a real email via mail.ter.vn:465.

Usage:
    cd backend
    uv run python scripts/test_smtp.py your@email.com
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make sure app packages are on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.modules.notifications.infrastructure.email_adapter import build_email_adapter


async def main(to_address: str) -> None:
    adapter = build_email_adapter()
    print(f"Adapter: {type(adapter).__name__}")

    html = f"""
<div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
  <h2 style="margin:0 0 8px">VinUni Career Platform</h2>
  <p style="color:#555; margin:0 0 24px">SMTP smoke test — gửi thành công!</p>
  <div style="background:#f5f5f5; border-radius:12px; padding:20px;">
    <p style="margin:0; font-size:14px; color:#333">
      ✅ Server: <strong>mail.ter.vn:465 (SSL)</strong><br>
      ✅ From: <strong>no-reply@ter.vn</strong><br>
      ✅ To: <strong>{to_address}</strong>
    </p>
  </div>
  <p style="color:#999; font-size:12px; margin-top:24px">
    Đây là email tự động từ hệ thống. Vui lòng không trả lời.
  </p>
</div>
"""

    try:
        await adapter.send(
            to=to_address,
            subject="[VinUni Test] SMTP hoạt động ✓",
            body=html,
        )
        print(f"✅  Email sent successfully to {to_address}")
    except Exception as e:
        print(f"❌  Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    to = sys.argv[1] if len(sys.argv) > 1 else "danielngo0302@gmail.com"
    asyncio.run(main(to))
