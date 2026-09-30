"""Idempotently seeds the DESIGN.md 9 flow-2 demo chain: "likes Python" ->
"recommend Django" -> "recommend FastAPI". The actual seeding logic lives in
app/services/demo_seed.py, shared with POST /admin/reset so a
demo reset doesn't drift from what this script seeds.

Safe to re-run against a fresh docker-compose volume: checks for the fixed
seed conversation_id in `provenance` first and exits early if already seeded.

Usage (from backend/, with the venv active): python scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.demo_seed import seed_demo


async def main() -> None:
    settings = get_settings()

    async with async_session_factory() as db:
        lines = await seed_demo(db, settings)
        if lines is None:
            print("Demo chain already seeded (conversation_id matches) -- skipping.")
            return

        await db.commit()
        for line in lines:
            print(line)
        print("Seed chain complete: likes Python -> recommend Django -> recommend FastAPI")


if __name__ == "__main__":
    asyncio.run(main())
