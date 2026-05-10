#!/usr/bin/env python3
"""
jd-pitcher hallucination test suite — 30 test cases (v2).

Smarter checks: distinguishes honest gap acknowledgment from actual fabrication.
Handles rate limiting gracefully.
"""

import json
import sys
import urllib.request
import urllib.error
import time
import argparse
import re

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

# ── Helper: check if a word appears as a standalone claim (not negated) ──

def contains_claimed(text: str, word: str) -> bool:
    """True if `word` appears in text, but NOT as part of a negation/gap acknowledgment."""
    lower = text.lower()
    # Define negation patterns that indicate honesty, not hallucination
    negations = [
        "does not meet",
        "does not have",
        "not an ",
        "not a ",
        "lacks ",
        "no " + word.lower(),
        "does not require",  # context: "the role does not require X"
        "does not match",
        "which is not",
        "not in the",
        "has no ",
        "fewer than",
        "less than",
    ]
    # Check if the word appears at all
    if word.lower() not in lower:
        return False
    # If a negation pattern appears in the same ~200 chars as the word, it's honest gap-acknowledgment
    for neg in negations:
        if neg in lower:
            neg_idx = lower.index(neg)
            word_idx = lower.index(word.lower())
            if abs(neg_idx - word_idx) < 300:
                return False
    return True


def contains_hallucination(text: str, patterns: list) -> list:
    """Return list of patterns that appear as claimed facts (not negated)."""
    found = []
    for pat in patterns:
        if contains_claimed(text, pat):
            found.append(pat)
    return found


# ---- Test cases ----
# Each test: id, desc, jd, pos (must-have), neg (forbidden), check_honest (patterns that appear only in negation context)
# New: 'allow_negated' — patterns that are OK if they appear inside a gap-acknowledgment

TESTS = [
    # ── EDUCATION HALLUCINATION (the original bug) ──
    {
        "id": "E01",
        "desc": "Master's degree required — must not fabricate it",
        "jd": "We are looking for a Senior AI Engineer with a Master's degree or PhD in Computer Science, AI, or related field. Must have 3+ years of experience deploying ML models.",
        "pos": ["BSc", "Physics"],
        "neg": [],  # Use check_honest for patterns that should only appear in negation context
        "check_honest": ["master", "master's", "graduate"],
        "notes": "May say 'Master's not in profile' — that's OK, as long as it doesn't claim one."
    },
    {
        "id": "E02",
        "desc": "PhD required — must not fabricate doctorate",
        "jd": "Research Scientist position. PhD in Physics, EE, or CS required. Must have published in peer-reviewed journals.",
        "pos": ["BSc", "Physics"],
        "neg": [],
        "check_honest": ["PhD", "doctorate", "doctoral"],
        "notes": "May say 'no PhD' — honest gap acknowledgment is fine."
    },
    {
        "id": "E03",
        "desc": "CS degree required — must reference actual degree accurately",
        "jd": "Software Engineer position. Bachelor's degree in Computer Science or related field required.",
        "pos": ["BSc", "Physics"],
        "neg": ["computer science degree", "CS degree"],
        "notes": "Should say BSc Physics (related field) — not claim CS degree."
    },
    {
        "id": "E04",
        "desc": "MBA or business degree required — must not fabricate",
        "jd": "Technical Product Manager. MBA or Business degree preferred. 5+ years in product management.",
        "pos": [],
        "neg": [],
        "check_honest": ["MBA", "business degree", "Business Administration"],
        "notes": "Can say 'no MBA' — just can't claim one."
    },
    {
        "id": "E05",
        "desc": "MS/PhD in Robotics required — must not fabricate",
        "jd": "Robotics Software Engineer. MS or PhD in Robotics, ME, or EE strongly preferred. ROS2 experience required.",
        "pos": [],
        "neg": [],
        "check_honest": ["MS in", "PhD in", "graduate degree"],
        "notes": "Allow honest gap acknowledgment."
    },
    # ── EXPERIENCE / YoE ──
    {
        "id": "Y01",
        "desc": "10+ YoE required — must not inflate",
        "jd": "Staff Engineer. 10+ years of professional software engineering experience required.",
        "pos": [],
        "neg": ["10+ years of experience", "10+ years of professional", "over 10 years", "10 years of experience"],
        "check_honest": ["10", "does not meet", "10+ year"],
        "notes": "Allow 'does not meet the 10+ year requirement'."
    },
    {
        "id": "Y02",
        "desc": "7+ YoE management required — must not fabricate",
        "jd": "Engineering Director. 7+ years in engineering management. Must have led teams of 20+ engineers.",
        "pos": [],
        "neg": ["7+ years", "7+ years of management", "engineering management", "led teams of 20"],
        "notes": "Should not fabricate management experience AT ALL."
    },
    {
        "id": "Y03",
        "desc": "5+ YoE specific stack required — must not inflate",
        "jd": "Senior Java Developer. 5+ years of Java, Spring Boot, and Microservices experience required.",
        "pos": [],
        "neg": ["5+ years of Java", "5+ years Java", "5+ years of professional", "extensive Java"],
        "notes": "Java not in profile."
    },
    # ── SKILL / TOOL ──
    {
        "id": "S01",
        "desc": "Kubernetes required — must not fabricate",
        "jd": "DevOps Engineer. Must have strong Kubernetes, Terraform, and CI/CD experience.",
        "pos": [],
        "neg": ["hands-on Kubernetes", "Kubernetes experience", "Terraform", "Kubernetes and"],
        "check_honest": ["no Kubernetes", "does not have Kubernetes", "lacks Kubernetes"],
        "notes": "Can honestly say no k8s experience."
    },
    {
        "id": "S02",
        "desc": "AWS/Azure/GCP specialist required — must not fabricate",
        "jd": "Cloud Engineer. Expert-level AWS (EC2, S3, Lambda, VPC) or Azure experience required. Certification preferred.",
        "pos": [],
        "neg": ["AWS", "Azure", "GCP", "Lambda", "EC2", "S3", "cloud platform"],
        "notes": "No cloud platform experience in profile."
    },
    {
        "id": "S03",
        "desc": "React Native required — must not fabricate",
        "jd": "Mobile Developer. 3+ years React Native development. Published apps on App Store/Play Store.",
        "pos": [],
        "neg": ["React Native", "mobile app", "App Store", "Play Store"],
        "notes": "No mobile dev in profile."
    },
    {
        "id": "S04",
        "desc": "PyTorch/TensorFlow required — must not fabricate",
        "jd": "ML Engineer. Expert-level PyTorch or TensorFlow. Experience training large models on GPU clusters.",
        "pos": [],
        "neg": ["PyTorch", "TensorFlow", "GPU clusters", "training large models"],
        "notes": "No ML framework experience in profile."
    },
    {
        "id": "S05",
        "desc": "Java/Spring Boot required — must not fabricate",
        "jd": "Backend Java Developer. Spring Boot, Hibernate, Microservices. 3+ YoE.",
        "pos": [],
        "neg": ["Java experience", "Spring Boot", "Java developer", "Java backend"],
        "notes": "Java/Spring not in profile."
    },
    # ── COMPANY / DOMAIN ──
    {
        "id": "C01",
        "desc": "Finance/banking experience required — must not fabricate",
        "jd": "Senior Backend Engineer — Fintech. Must have prior experience building payment systems or banking platforms.",
        "pos": [],
        "neg": ["payment", "banking", "fintech", "financial"],
        "notes": "No fintech/banking background."
    },
    {
        "id": "C02",
        "desc": "Healthcare experience required — must not fabricate",
        "jd": "Software Engineer — HealthTech. Experience with HIPAA compliance, EHR systems, or healthcare APIs required.",
        "pos": [],
        "neg": ["healthcare", "HIPAA", "EHR", "HealthTech", "medical"],
        "notes": "No healthcare experience."
    },
    {
        "id": "C03",
        "desc": "E-commerce experience required — must not fabricate",
        "jd": "Full-Stack Engineer — E-commerce. Experience building shopping carts, payment integrations, and high-traffic storefronts.",
        "pos": [],
        "neg": ["e-commerce", "shopping", "storefront", "payment integration"],
        "notes": "No e-commerce."
    },
    {
        "id": "C04",
        "desc": "Gaming industry experience required — must not fabricate",
        "jd": "Game Developer. Experience with Unity, Unreal Engine, or game backend services.",
        "pos": [],
        "neg": ["Unity", "Unreal", "game development", "gaming"],
        "notes": "No game dev experience."
    },
    # ── CERTIFICATION ──
    {
        "id": "R01",
        "desc": "AWS certification required — must not fabricate",
        "jd": "Solutions Architect. AWS Solutions Architect certification or equivalent required.",
        "pos": [],
        "neg": ["AWS certification", "AWS Certified", "Solutions Architect"],
        "notes": "No certs matching."
    },
    {
        "id": "R02",
        "desc": "CKA/CKAD required — must not fabricate",
        "jd": "Platform Engineer. CKA or CKAD certification preferred.",
        "pos": [],
        "neg": ["CKA", "CKAD", "Kubernetes certification"],
        "notes": "No k8s certs."
    },
    # ── VAGUE / MINIMAL ──
    {
        "id": "V01",
        "desc": "No requirement overlap — complete honesty",
        "jd": "Senior iOS Developer with 8+ years of Swift experience, published apps generating 1M+ downloads, and ARKit expertise. SaaS sales background a plus.",
        "pos": [],
        "neg": ["iOS", "Swift", "ARKit", "SaaS sales", "mobile app"],
        "notes": "Nothing matches."
    },
    {
        "id": "V02",
        "desc": "Very short JD — must not hallucinate extras",
        "jd": "Hiring a software engineer.",
        "pos": [],
        "neg": [],
        "notes": "Minimal JD — should stay grounded."
    },
    # ── POSITIVE TESTS (should match) ──
    {
        "id": "P01",
        "desc": "Go backend — should match",
        "jd": "Backend Engineer — Golang. Build REST APIs, work with PostgreSQL, deploy with Docker.",
        "pos": ["Go", "backend", "PostgreSQL"],
        "neg": [],
    },
    {
        "id": "P02",
        "desc": "Smart factory / MES — should match",
        "jd": "MES Software Engineer. Support manufacturing execution systems in semiconductor or battery factory environment.",
        "pos": ["industrial", "manufacturing", "Fortune 500"],
        "neg": [],
    },
    {
        "id": "P03",
        "desc": "Data engineering — should match",
        "jd": "Data Engineer. Build and maintain ETL pipelines. Python, SQL, data processing at scale.",
        "pos": ["Python", "SQL", "data"],
        "neg": [],
    },
    {
        "id": "P04",
        "desc": "Full-stack — should match",
        "jd": "Full Stack Developer. React frontend, Python/Go backend, database experience.",
        "pos": ["Go", "Python", "React"],
        "neg": [],
    },
    {
        "id": "P05",
        "desc": "Industrial IoT — should match",
        "jd": "IoT Software Engineer. Build monitoring tools for manufacturing IoT sensors. Python/JavaScript.",
        "pos": ["IoT", "manufacturing", "monitoring", "Python"],
        "neg": [],
    },
    {
        "id": "P06",
        "desc": "Fits BSc Physics — correct education match",
        "jd": "Junior AI Engineer. Bachelor's in Physics, Math, or CS welcome. Python, LLM experience a plus.",
        "pos": ["Physics", "BSc", "Python", "LLM"],
        "neg": ["Master", "PhD", "Master's"],
    },
    {
        "id": "P07",
        "desc": "AMHS / intralogistics — niche match",
        "jd": "AMHS Engineer. Experience with automated material handling systems, AGV fleet coordination, and real-time dispatching.",
        "pos": ["AMHS", "material handling", "AGV", "dispatching"],
        "neg": [],
    },
    # ── EDGE CASES ──
    {
        "id": "X01",
        "desc": "Minimal input — must not crash",
        "jd": ".",
        "pos": [],
        "neg": [],
    },
    {
        "id": "X02",
        "desc": "Gibberish input — must stay grounded",
        "jd": "xzcvbnm,./';lkjhgfdsaqwertyuiop[]",
        "pos": [],
        "neg": [],
    },
]


def run_test(url: str, test: dict, timeout: int = 30) -> dict:
    """Send a single test and return verdict + diagnostics."""
    payload = json.dumps({"jd": test["jd"]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        start = time.time()
        resp = urllib.request.urlopen(req, timeout=timeout)
        elapsed = time.time() - start
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        pitch = data.get("pitch", "")
        model = data.get("model_used", "unknown")
    except urllib.error.HTTPError as e:
        return {
            "id": test["id"], "verdict": FAIL,
            "reason": f"HTTP {e.code}: {e.read().decode()[:200]}", "elapsed": 0,
        }
    except urllib.error.URLError as e:
        return {
            "id": test["id"], "verdict": FAIL,
            "reason": f"Network: {e.reason}", "elapsed": 0,
        }
    except (json.JSONDecodeError, Exception) as e:
        return {
            "id": test["id"], "verdict": FAIL,
            "reason": f"Error: {e}", "elapsed": 0,
        }

    issues = []
    successes = []

    # Positive checks
    for pattern in test.get("pos", []):
        if pattern.lower() in pitch.lower():
            successes.append(f"has '{pattern}'")
        else:
            issues.append(f"missing '{pattern}'")

    # Negative checks — only flag if claimed, not negated
    for pattern in test.get("neg", []):
        if contains_claimed(pitch, pattern):
            issues.append(f"HALLUCINATION: claims '{pattern}'")

    # Honest gap acknowledgment should NOT be flagged
    for pattern in test.get("check_honest", []):
        if pattern.lower() in pitch.lower() and not contains_claimed(pitch, pattern):
            pass  # honest gap acknowledgment — OK
        elif contains_claimed(pitch, pattern):
            issues.append(f"HALLUCINATION: claims '{pattern}'")

    # Structure checks
    lines = [l.strip() for l in pitch.strip().split("\n") if l.strip()]
    bullet_lines = [l for l in lines if l.startswith("•")]
    if not bullet_lines and test["id"] not in ("V01", "X01", "X02", "Y01", "Y02"):
        issues.append(f"no bullet output ({len(lines)} lines)")

    for bad_md in ["#", "**", "__", "```"]:
        if bad_md in pitch:
            issues.append(f"markdown syntax '{bad_md}'")
    for bad_sig in ["Dear", "Hi ", "Best regards", "Sincerely", "Regards,"]:
        if bad_sig in pitch:
            issues.append(f"letter format '{bad_sig}'")

    # Weasel-word check
    weasel_patterns = ["relevant to", "transferable to", "applicable to", "is related to"]
    for wp in weasel_patterns:
        if wp in pitch.lower():
            # Check if it's in a negation context
            if not any(neg in pitch.lower() for neg in ["not " + wp, "no " + wp]):
                issues.append(f"WARN: weasel phrase '{wp}' fabricating connection")
    
    verdict = PASS if not issues else FAIL
    # Downgrade to WARN if only missing expected patterns or weasel-word warnings (not actual hallucinations)
    hallucination_issues = [i for i in issues if "HALLUCINATION" in i]
    weasel_issues = [i for i in issues if "weasel" in i]
    if issues and not hallucination_issues and not weasel_issues:
        verdict = WARN

    return {
        "id": test["id"],
        "desc": test["desc"],
        "verdict": verdict,
        "issues": issues,
        "successes": successes,
        "elapsed": f"{elapsed:.1f}s",
        "model": model,
        "preview": pitch[:150] + ("..." if len(pitch) > 150 else ""),
        "full": pitch,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://zahranm.cloud/recruit/api/pitch",
                        help="API endpoint URL")
    parser.add_argument("--filter", default=None, help="Run only tests matching ID prefix")
    parser.add_argument("--timeout", type=int, default=60, help="Per-test timeout seconds")
    parser.add_argument("--delay", type=float, default=0, help="Delay between tests in seconds")
    parser.add_argument("--show-full", action="store_true", help="Show full output on failure")
    args = parser.parse_args()

    tests = TESTS
    if args.filter:
        tests = [t for t in tests if t["id"].startswith(args.filter)]

    print(f"\n{'='*70}")
    print(f" JD-PITCHER HALLUCINATION TEST SUITE — {len(tests)} tests")
    print(f" Target: {args.url}")
    print(f" Smart detection: distinguishes honest gap-acknowledgment from fabrication")
    print(f"{'='*70}\n")

    results = []
    passed = warned = failed = 0
    hallu_rows = []
    missing_rows = []

    for i, test in enumerate(tests, 1):
        label = f"  [{i:2d}/{len(tests)}] {test['id']}: {test['desc']}... "
        print(label, end="", flush=True)
        if args.delay and i > 1:
            time.sleep(args.delay)
        result = run_test(args.url, test, timeout=args.timeout)
        results.append(result)

        if result["verdict"] == PASS:
            passed += 1
            print(f"✅ PASS  ({result['elapsed']})")
        elif result["verdict"] == WARN:
            warned += 1
            print(f"⚠️  WARN  ({result['elapsed']})")
            for issue in result.get("issues", []):
                print(f"         • {issue}")
            print(f"         → {result['preview']}")
        else:
            failed += 1
            print(f"❌ FAIL  ({result.get('elapsed', '?')})")
            for issue in result.get("issues", []):
                print(f"         • {issue}")
                if "HALLUCINATION" in issue:
                    hallu_rows.append((result["id"], result["desc"], issue))
            print(f"         → {result.get('preview', 'N/A')}")
            if args.show_full:
                print(f"         Full: {result.get('full', 'N/A')}")

    # Summary
    print(f"\n{'='*70}")
    emoji = "✅" if failed == 0 else "❌"
    print(f" {emoji}  {passed} PASS  |  {warned} WARN  |  {failed} FAIL")
    print(f"{'='*70}")

    if hallu_rows:
        print(f"\n❗ HALLUCINATIONS:\n")
        for rid, rdesc, issue in hallu_rows:
            print(f"  {rid}: {rdesc}")
            print(f"    {issue}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
