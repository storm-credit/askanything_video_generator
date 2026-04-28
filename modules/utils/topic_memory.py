"""Canonical topic memory for cross-channel duplicate detection."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from typing import Iterable


DB_PATH = os.path.join("data", "topic_memory.db")
UPLOAD_HISTORY_DB_PATH = os.path.join("data", "upload_history.db")


TOPIC_CANONICAL_PATTERNS: list[tuple[str, list[str]]] = [
    ("black_hole_time", [r"블랙홀", r"black\s*hole", r"agujero\s*negro"]),
    ("saturn_moon_ring_cycle", [
        r"토성.*(?:고리|달|위성)",
        r"토성.*(?:녹|부서|사라지|비|강|호수)",
        r"고리.*달",
        r"saturn.*(?:ring|moon|titan)",
        r"titan.*(?:rain|river|lake)",
        r"saturno.*(?:anillo|luna|tit[aá]n)",
    ]),
    ("frankfurt_roman_sanctuary", [
        r"프랑크푸르트",
        r"frankfurt",
        r"로마\s*(?:성역|성소)",
        r"roman\s+(?:sanctuary|shrine)",
        r"romanos?.*frankfurt",
    ]),
    ("deep_sea_new_species", [
        r"심해.*(?:신종|종\s*발견|산호초)",
        r"아르헨티나.*심해",
        r"deep\s*sea.*(?:species|coral)",
        r"abis[mo].*(?:especie|criatura)",
    ]),
    ("deep_sea_24_species", [
        r"심해.*24\s*종",
        r"24\s*종.*(?:생명체|신종|종)",
        r"deep\s*sea.*24\s*(?:species|life)",
        r"24\s*(?:especies|criaturas).*(?:abismo|profund)",
    ]),
    ("undersea_river_brine", [
        r"바다\s*밑.*강",
        r"바닷속.*강",
        r"해저.*강",
        r"죽은\s*강",
        r"바닷속.*폭포",
        r"undersea.*river",
        r"brine.*pool",
        r"r[ií]o.*debajo.*mar",
    ]),
    ("earth_like_exoplanet", [
        r"hd\s*137010",
        r"지구\s*(?:닮은|형).*(?:외계|행성)",
        r"화성보다\s*추운.*행성",
        r"earth\s*like.*(?:exoplanet|planet)",
        r"planeta.*(?:gemelo|id[eé]ntico).*(?:tierra|earth)",
    ]),
    ("egypt_animal_tomb", [
        r"이집트.*(?:800구|동물\s*무덤|동물\s*묘지)",
        r"egypt.*animal.*(?:tomb|cemetery|mumm)",
        r"egipto.*(?:tumba|momias?).*animales?",
    ]),
    ("mantle_ocean_660km", [
        r"맨틀.*바다",
        r"660\s*km.*(?:지하|물|바다)",
        r"지하\s*660",
        r"mantle.*ocean",
        r"ocean.*earth'?s\s*mantle",
        r"oc[eé]ano.*(?:bajo|debajo).*(?:tierra|pies)",
    ]),
    ("ancient_ice_air", [r"80만\s*년.*공기", r"빙하.*공기", r"ancient.*air.*ice"]),
    ("deep_sea_10000m", [r"심해\s*(?:1만|10000|10,000)\s*미터", r"deep\s*sea\s*(?:10000|10,000)"]),
    ("octopus_blue_blood", [
        r"문어.*파랗",
        r"octopus.*(?:blue\s*blood|three\s*hearts)",
        r"animal\s*with\s*three\s*hearts",
        r"pulpo.*(?:sangre|azul|corazones?)",
    ]),
    ("moon_disappears", [
        r"달이\s*사라",
        r"moon\s*(?:vanish|disappear)",
        r"luna\s*desapare",
    ]),
    ("dinosaur_weapons_top3", [
        r"티라노보다\s*무서운\s*공룡\s*무기",
        r"3\s*dinosaur\s*weapons.*t\.?\s*rex",
        r"3\s*armas\s*de\s*dinosaurio.*t\.?\s*rex",
    ]),
    ("nanotyrannus_not_baby_trex", [
        r"나노티라누스",
        r"어린\s*티라노.*아니",
        r"t\.?\s*rex.*(?:lie|young|baby).*",
        r"baby\s*t\.?\s*rex.*(?:exist|fake|lie)",
        r"joven\s*t\.?\s*rex",
        r"beb[eé]\s*t\.?\s*rex",
    ]),
    ("europa_oxygen_ocean", [
        r"유로파.*산소",
        r"ice\s*(?:moon|planet).*(?:oxygen|breathe|life)",
        r"moon\s*makes\s*its\s*own\s*oxygen",
        r"europa.*oxygen",
        r"luna.*(?:ox[ií]geno|respirar|vida)",
    ]),
    ("spinosaurus_aquatic", [
        r"스피노사우루스",
        r"spinosaurus",
        r"espinosaur",
    ]),
]


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_topic_memory (
                canonical_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'upload_history',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (canonical_key, channel, normalized_title)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_canonical_topic_memory_key
            ON canonical_topic_memory(canonical_key)
            """
        )


def normalize_title(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]", " ", text or "")
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣áéíóúüñ¿?]+", "", text)
    return text.strip()


def extract_topic_key(text: str) -> str | None:
    compact = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not compact:
        return None
    for key, patterns in TOPIC_CANONICAL_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, compact, re.IGNORECASE):
                return key
    return None


def upsert_titles(channel: str, titles: Iterable[str], source: str = "upload_history") -> int:
    ensure_db()
    now = datetime.now().isoformat()
    rows: list[tuple[str, str, str, str, str, str]] = []
    for title in titles:
        clean = str(title or "").strip()
        if not clean:
            continue
        key = extract_topic_key(clean)
        if not key:
            continue
        rows.append((key, channel, clean, normalize_title(clean), source, now))

    if not rows:
        return 0

    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO canonical_topic_memory
                (canonical_key, channel, title, normalized_title, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_key, channel, normalized_title) DO UPDATE SET
                title=excluded.title,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def sync_from_upload_history() -> int:
    ensure_db()
    if not os.path.exists(UPLOAD_HISTORY_DB_PATH):
        return 0

    src = sqlite3.connect(UPLOAD_HISTORY_DB_PATH)
    src.row_factory = sqlite3.Row
    try:
        rows = src.execute(
            "SELECT channel, title FROM youtube_uploads ORDER BY published_at DESC, fetched_at DESC"
        ).fetchall()
    finally:
        src.close()

    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(str(row["channel"]), []).append(str(row["title"]))

    total = 0
    for channel, titles in grouped.items():
        total += upsert_titles(channel, titles, source="upload_history_sync")
    return total


def get_memory_summary() -> list[dict[str, object]]:
    ensure_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT canonical_key, COUNT(*) AS cnt, COUNT(DISTINCT channel) AS channels
            FROM canonical_topic_memory
            GROUP BY canonical_key
            ORDER BY cnt DESC, canonical_key ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
