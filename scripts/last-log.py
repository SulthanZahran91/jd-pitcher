#!/usr/bin/env python3
import argparse
import sqlite3
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "logs.sqlite"

parser = argparse.ArgumentParser(description="Show recent jd-pitcher submissions and generated answers.")
parser.add_argument("-n", "--limit", type=int, default=1, help="number of entries to show")
parser.add_argument("--compact", action="store_true", help="single-line summary only")
args = parser.parse_args()

if not DB.exists():
    raise SystemExit(f"Missing log DB: {DB}")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cols = {row[1] for row in con.execute("PRAGMA table_info(requests)")}
select_jd = "jd_text" if "jd_text" in cols else "jd_prefix"
select_pitch = "pitch_text" if "pitch_text" in cols else "''"

rows = con.execute(f"""
    SELECT id, timestamp, jd_length, model_used, status,
           COALESCE({select_jd}, jd_prefix, '') AS jd_text,
           COALESCE({select_pitch}, '') AS pitch_text
    FROM requests
    ORDER BY id DESC
    LIMIT ?
""", (args.limit,)).fetchall()

if not rows:
    print("No submissions logged yet.")
    raise SystemExit(0)

for idx, row in enumerate(rows):
    if idx:
        print("\n" + "=" * 72 + "\n")

    jd = (row["jd_text"] or "").strip()
    pitch = (row["pitch_text"] or "").strip()

    if args.compact:
        jd_one = " ".join(jd.split())[:120]
        pitch_one = " ".join(pitch.split())[:160]
        print(f"#{row['id']} {row['timestamp']} {row['status']} {row['model_used']} JD={row['jd_length']} | {jd_one} | {pitch_one}")
        continue

    print(f"ID: {row['id']}")
    print(f"Time: {row['timestamp']}")
    print(f"Status: {row['status']}")
    print(f"Model: {row['model_used']}")
    print(f"JD length: {row['jd_length']}")
    print("\nSUBMISSION:")
    print(textwrap.fill(jd or "(not stored for older rows)", width=100))
    print("\nANSWER:")
    print(pitch or "(not stored for older rows; new successful requests will store the answer)")
