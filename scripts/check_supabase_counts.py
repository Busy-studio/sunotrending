#!/usr/bin/env python3
from pathlib import Path
import os
from supabase import create_client


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_dotenv(Path(".env"))
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
for table in ["suno_songs", "suno_song_history", "suno_rank_history", "suno_song_archive", "manual_song_queue", "app_payloads"]:
    res = sb.table(table).select("*", count="exact").limit(1).execute()
    print(f"{table}: {res.count}")
