#!/usr/bin/env python3
"""
Sync source_of_truth.md → jd-pitcher profile.yaml + masks.yaml.

Idempotent: only writes files and triggers rebuild if content changed.
Usage:
    python3 scripts/sync_profile.py              # dry-run: show what would change
    python3 scripts/sync_profile.py --apply      # write files + rebuild Docker
    python3 scripts/sync_profile.py --force      # force rebuild even if no changes
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
SOURCE_PATH = "/home/dev/job_applications/source_of_truth.md"
PROFILE_PATH = os.path.join(PROJECT_DIR, "config", "profile.yaml")
MASKS_PATH = os.path.join(PROJECT_DIR, "config", "masks.yaml")
STATE_FILE = os.path.expanduser("~/.jd-pitcher-sync-state.json")


def parse_source(path: str) -> dict:
    """Parse source_of_truth.md into structured data."""
    with open(path) as f:
        text = f.read()

    data = {
        "name": "",
        "tagline": "",
        "education": "",
        "experience": [],
        "projects": [],
        "skills": [],
        "meta": {"interests": [], "location": "Jakarta, Indonesia"},
        "masks": {},
    }

    lines = text.split("\n")

    # Extract name from h1
    for line in lines:
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            title = m.group(1).strip()
            # "Sulthan Zahran Ma'ruf — Master Source of Truth" → "Sulthan Zahran"
            data["name"] = title.split(" —")[0].split("–")[0].split(" -")[0].strip()
            break

    # Extract tagline from Professional Identity
    for i, line in enumerate(lines):
        if "Core Identity:" in line:
            # Format: "**Core Identity:** Hardware-software integration ..."
            rest = line.split("**Core Identity:**", 1)[-1].strip()
            # "Hardware-software integration engineer specializing in ..."
            # Take first sentence or first ~80 chars
            tagline = rest.split(".")[0].strip()
            if len(tagline) > 100:
                tagline = tagline[:97] + "..."
            data["tagline"] = tagline
            break

    # Parse sections by ## header
    current_section = None
    section_lines = {}

    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            current_section = m.group(1).strip()
            section_lines[current_section] = []
        elif current_section:
            section_lines.setdefault(current_section, []).append(line)

    # --- Education ---
    edu_section = section_lines.get("Education", [])
    edu_text = "\n".join(edu_section)
    degree_m = re.search(r"\*\*(.+?)\*\*", edu_text)
    if degree_m:
        data["education"] = degree_m.group(1).strip()
    else:
        # Fallback: look for "Bachelor of Science"
        bs_m = re.search(r"Bachelor of Science[^)]*\)", edu_text)
        data["education"] = bs_m.group(0).strip() if bs_m else ""

    # --- Experience ---
    exp_section = section_lines.get("Professional Experience", [])
    current_company = None
    current_highlights = []
    current_role = ""
    current_duration = ""
    company_order = []

    for line in exp_section:
        # ### Company — Role
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            # Save previous company
            if current_company and current_role:
                company_order.append({
                    "company": current_company,
                    "role": current_role,
                    "duration": current_duration,
                    "highlights": current_highlights[:3],  # top 3
                    "all_highlights": current_highlights,
                })
            # Parse new company
            rest = m.group(1).strip()
            # Split by em-dash or regular dash
            parts = re.split(r"\s*[—–-]\s*", rest, maxsplit=1)
            if len(parts) >= 2:
                current_company = parts[0].strip()
                current_role = parts[1].strip()
            else:
                current_company = rest
                current_role = ""
            current_highlights = []
            current_duration = ""
        elif line.strip().startswith("**") and "** |" in line and "**" in line:
            # Duration line: "**April 2024 – Present | Karawang, ...**"
            dur_m = re.match(r"\*\*(.+?)\*\*", line)
            if dur_m:
                current_duration = dur_m.group(1).strip().split(" |")[0].strip()
            current_role = ""
        elif line.strip().startswith("- ") and ":" not in line.split("- ", 1)[-1][:5]:
            highlight = line.strip().lstrip("- ").strip()
            # Filter out section headers and long descriptions
            if not highlight.startswith("**") and len(highlight) > 15:
                current_highlights.append(highlight)

    # Save last company
    if current_company and current_role:
        company_order.append({
            "company": current_company,
            "role": current_role,
            "duration": current_duration,
            "highlights": current_highlights[:3],
            "all_highlights": current_highlights,
        })

    # Pick top 3-4 most relevant experience entries
    # Prioritize: current job > international deployment > research > other
    priority_keywords = ["LG Sinarmas", "Korea", "Research", "PLC", "Freelance"]
    scored = []
    for idx, entry in enumerate(company_order):
        score = 0
        for kw in priority_keywords:
            if kw.lower() in entry["company"].lower() or kw.lower() in entry.get("role", "").lower():
                score += 1
        scored.append((score, idx, entry))
    scored.sort(key=lambda x: -x[0])

    # Generate company_ref and build masks
    used_refs = {}
    for _, _, entry in scored[:4]:
        company_name = entry["company"]
        # Create a ref key
        base_ref = re.sub(r"[^a-z0-9]+", "_", company_name.lower()).strip("_")
        if not base_ref:
            base_ref = "unknown"
        ref = base_ref
        counter = 1
        while ref in used_refs:
            counter += 1
            ref = f"{base_ref}_{counter}"
        used_refs[company_name] = ref

        # Create mask
        mask_text = anonymize_company(company_name)
        data["masks"][ref] = mask_text

        # Build experience entry
        exp_entry = {
            "role": entry["role"],
            "company_ref": ref,
            "duration": entry.get("duration", ""),
            "highlights": entry["highlights"],
        }
        data["experience"].append(exp_entry)

    # --- Projects ---
    proj_section = section_lines.get("Projects & Tools", [])
    all_projects = []
    current_cat = "Other"
    for line in proj_section:
        cm = re.match(r"^###\s+(.+)$", line)
        if cm:
            current_cat = cm.group(1).strip()
        elif line.strip().startswith("**") and "** — " in line:
            parts = line.strip().split("** — ", 1)
            name = parts[0].replace("**", "").strip()
            desc = parts[1].strip()
            # Extract tech stack from desc if in (parentheses)
            tech = ""
            tech_m = re.search(r"\(([^)]+)\)", desc)
            if tech_m:
                tech = tech_m.group(1).strip()
            all_projects.append({
                "name": name,
                "description": desc,
                "category": current_cat,
            })
        elif line.strip().startswith("- **") and "** " in line:
            parts = line.strip().lstrip("- ").split("** ", 1)
            name = parts[0].replace("**", "").strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
            all_projects.append({
                "name": name,
                "description": desc,
                "category": current_cat,
            })

    # Pick top 6 projects
    # Published/collaborative projects > tools > side projects
    for proj in all_projects[:6]:
        # Generate GitHub URL if it's a known project
        known_urls = {
            "Clanker": "https://github.com/SulthanZahran91/clanker",
            "Timing Diagram Analyzer": "",
            "IoT Sensor Monitoring Automation": "",
            "PLC Log Waveform Visualizer": "",
            "SECS/GEM Southbound Simulator": "",
            "SECS/GEM Log Visualizer MVP": "",
            "Korean-English Meeting Transcription Pipeline": "",
            "Siklus": "",
            "Throughput": "",
            "Keliling UI": "",
            "BeanDaru": "",
            "Spectroscopic Analysis GUI": "",
        }
        url = known_urls.get(proj["name"], "")
        data["projects"].append({
            "name": proj["name"],
            "url": url,
            "description": proj["description"][:120],
        })

    # --- Skills ---
    skills_section = section_lines.get("Technical Skills", [])
    current_skill_cat = None
    current_skill_items = []
    for line in skills_section:
        cm = re.match(r"^###\s+(.+)$", line)
        if cm:
            if current_skill_cat and current_skill_items:
                data["skills"].append({
                    "category": current_skill_cat,
                    "items": current_skill_items[:6],  # top 6 per category
                })
            current_skill_cat = cm.group(1).strip()
            current_skill_items = []
        elif line.strip().startswith("- "):
            item = line.strip().lstrip("- ").strip()
            # Skip parenthetical elaborations and long descriptions
            if len(item) > 80:
                continue
            # Extract just the bolded skill name if available
            bm = re.match(r"\*\*(.+?)\*\*", item)
            if bm:
                item = bm.group(1).strip()
            current_skill_items.append(item)

    if current_skill_cat and current_skill_items:
        data["skills"].append({
            "category": current_skill_cat,
            "items": current_skill_items[:6],
        })

    # --- Meta ---
    data["meta"]["interests"] = ["industrial IoT", "intralogistics", "physics-informed ML"]

    return data


def anonymize_company(name: str) -> str:
    """Generate an anonymized description for a company."""
    company_masks = {
        "LG Sinarmas Technology Solutions": "a Fortune 500 industrial conglomerate in Southeast Asia",
        "LG ENSOL Ochang Factory": "an international factory deployment in South Korea",
        "PT Polychemie Asia Pacific Permai": "a chemical manufacturing plant in Indonesia",
        "University of Indonesia": "a university physics research lab",
        "PT. Sugitama Intiarto": "an industrial automation integrator",
        "Tim Robotika Universitas Indonesia": "a university robotics lab",
    }
    for key, mask in company_masks.items():
        if key.lower() in name.lower():
            return mask
    return f"a company in the {name.split()[-1]} sector"


def yaml_serialize(data: dict) -> str:
    """Serialize to YAML matching the existing format."""
    # We use collections.OrderedDict to maintain field order
    result = []
    result.append(f"name: \"{data['name']}\"")
    result.append(f"tagline: \"{data['tagline']}\"")
    result.append(f"education: \"{data['education']}\"")
    result.append("")

    # Experience
    result.append("experience:")
    for exp in data["experience"]:
        result.append(f"  - role: \"{exp['role']}\"")
        result.append(f"    company_ref: \"{exp['company_ref']}\"")
        result.append(f"    duration: \"{exp['duration']}\"")
        result.append("    highlights:")
        for h in exp["highlights"]:
            result.append(f"      - \"{h}\"")
    result.append("")

    # Projects
    result.append("projects:")
    for proj in data["projects"]:
        result.append(f"  - name: \"{proj['name']}\"")
        result.append(f"    url: \"{proj['url']}\"")
        result.append(f"    description: \"{proj['description']}\"")
    result.append("")

    # Skills
    result.append("skills:")
    for sk in data["skills"]:
        result.append(f"  - category: \"{sk['category']}\"")
        items_str = ", ".join(f"\"{i}\"" for i in sk["items"])
        result.append(f"    items: [{items_str}]")
    result.append("")

    # Meta
    meta = data["meta"]
    interests_str = ", ".join(f"\"{i}\"" for i in meta["interests"])
    result.append("meta:")
    result.append(f"  interests: [{interests_str}]")
    result.append(f"  location: \"{meta['location']}\"")
    result.append(f"  visa_status: \"{meta.get('visa_status', '')}\"")
    result.append("")

    return "\n".join(result)


def yaml_serialize_masks(masks: dict) -> str:
    """Serialize masks.yaml."""
    result = ["entities:"]
    for key in sorted(masks.keys()):
        result.append(f"  {key}: \"{masks[key]}\"")
    result.append("")
    return "\n".join(result)


def file_hash(path: str) -> str:
    """SHA256 of file, empty string if missing."""
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_if_changed(path: str, content: str, dry_run: bool = False) -> bool:
    """Write file only if content differs. Returns True if would write / written."""
    old_hash = file_hash(path)
    new_hash = hashlib.sha256(content.encode()).hexdigest()
    if old_hash == new_hash:
        return False
    if dry_run:
        return True
    with open(path, "w") as f:
        f.write(content)
    return True


def rebuild_docker():
    """Rebuild and restart the jd-pitcher Docker container."""
    print("→ Rebuilding Docker container...")
    result = subprocess.run(
        ["docker", "compose", "build"],
        cwd=PROJECT_DIR,
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"  BUILD FAILED:\n{result.stderr}")
        return False

    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=PROJECT_DIR,
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"  DEPLOY FAILED:\n{result.stderr}")
        return False

    print("  Docker container rebuilt and restarted.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sync source_of_truth.md → jd-pitcher profile")
    parser.add_argument("--apply", action="store_true", help="Write files and rebuild Docker")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if no changes")
    args = parser.parse_args()

    if not os.path.exists(SOURCE_PATH):
        print(f"ERROR: source_of_truth.md not found at {SOURCE_PATH}")
        sys.exit(1)

    # Track source file modification time to skip redundant checks
    current_mtime = os.path.getmtime(SOURCE_PATH)
    last_check = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                last_check = json.load(f)
            except (json.JSONDecodeError, ValueError):
                last_check = {}

    if not args.force and not args.apply:
        last_mtime = last_check.get("source_mtime", 0)
        if current_mtime <= last_mtime:
            print(f"source_of_truth.md has not been modified since last check ({last_check.get('checked_at', 'unknown')}).")
            print("Nothing to sync. (Use --force to override.)")
            sys.exit(0)

    print(f"Reading: {SOURCE_PATH}")
    data = parse_source(SOURCE_PATH)

    profile_yaml = yaml_serialize(data)
    masks_yaml = yaml_serialize_masks(data["masks"])

    print(f"\nExtracted profile:")
    print(f"  Name:      {data['name']}")
    print(f"  Tagline:   {data['tagline'][:60]}...")
    print(f"  Education: {data['education']}")
    print(f"  Experience: {len(data['experience'])} entries")
    for exp in data['experience']:
        print(f"    - {exp['role']} ({exp['company_ref']})")
    print(f"  Projects:  {len(data['projects'])} entries")
    print(f"  Skills:    {len(data['skills'])} categories")
    print(f"  Masks:     {len(data['masks'])} entries")

    profile_changed = write_if_changed(PROFILE_PATH, profile_yaml, dry_run=not args.apply)
    masks_changed = write_if_changed(MASKS_PATH, masks_yaml, dry_run=not args.apply)

    if profile_changed:
        print(f"\n✓ Updated: {PROFILE_PATH}")
    else:
        print(f"\n− No change: {PROFILE_PATH}")

    if masks_changed:
        print(f"✓ Updated: {MASKS_PATH}")
    else:
        print(f"− No change: {MASKS_PATH}")

    needs_rebuild = profile_changed or masks_changed or args.force

    # Save state
    with open(STATE_FILE, "w") as f:
        json.dump({
            "source_mtime": current_mtime,
            "checked_at": subprocess.run(
                ["date", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True
            ).stdout.strip(),
        }, f)

    if args.apply:
        if needs_rebuild:
            print("\nChanges detected. Rebuilding...")
            ok = rebuild_docker()
            sys.exit(0 if ok else 1)
        else:
            print("\nNo changes detected. Skipping rebuild.")
    else:
        if needs_rebuild:
            print("\n⚠ Dry-run: changes detected but --apply not set.")
            print("  Run with --apply to write files and rebuild Docker.")
        else:
            print("\nNo changes detected.")


if __name__ == "__main__":
    main()
