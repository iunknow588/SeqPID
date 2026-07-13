from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
REPORT_PATH = Path(__file__).with_name("sign_static_check_report.md")


CHECKS = [
    {
        "name": "trade side sign maps sell to negative",
        "path": SRC_DIR / "scheduler.py",
        "needles": [],
    },
    {
        "name": "trade signed amount uses side sign",
        "path": SRC_DIR / "scheduler.py",
        "needles": ["signed_amount = side_sign * amount"],
    },
    {
        "name": "active large signed amount uses active sign",
        "path": SRC_DIR / "scheduler.py",
        "needles": [
            "active_rule_signed_amount = active_sign * amount if is_active else signed_amount",
            'bucket["signed_large_active_amount"] += active_rule_signed_amount',
            'bucket["CH_rule_t"] += active_rule_signed_amount',
        ],
    },
    {
        "name": "rule event stores signed amount",
        "path": SRC_DIR / "capital_rule_engine.py",
        "needles": ["signed_amount=float(signed_amount or 0.0)"],
    },
    {
        "name": "rule window accumulates signed amount",
        "path": SRC_DIR / "capital_rule_engine.py",
        "needles": [
            "amount = float(event.signed_amount or 0.0)",
            "feature.CH_rule_t += amount",
            "feature.Q_rule_t += amount",
            "feature.R_seed_t += amount",
        ],
    },
    {
        "name": "legacy signed buckets keep signed amount",
        "path": SRC_DIR / "capital_rule_engine.py",
        "needles": [
            'bucket["signed_large_active_amount"] += event.signed_amount',
            'bucket["signed_mix_qr_amount"] += event.signed_amount',
        ],
    },
    {
        "name": "pid reads official signed rule fields",
        "path": SRC_DIR / "pid_decomposer_shared.py",
        "needles": [
            '"CH_rule_t"',
            '"Q_rule_t"',
            '"R_seed_t"',
            "explicit_mix = (explicit_q if np.isfinite(explicit_q) else 0.0) + (",
        ],
    },
    {
        "name": "capital model rule flow intention uses signed direction",
        "path": SRC_DIR / "capital_model.py",
        "needles": [
            '"rule_flow_signed_amount"',
            'intention = "涔板叆" if float(capital_source_debug["rule_flow_signed_amount"]) > 0 else "鍗栧嚭"',
        ],
    },
]


GROSS_FIELD_NOTES = [
    "signal_deal_buy_amount",
    "signal_deal_sell_amount",
    "large_active_buy_amount",
    "large_active_sell_amount",
    "small_passive_buy_amount",
    "small_passive_sell_amount",
]


def run_sign_contract_checks() -> tuple[list[dict], list[str]]:
    results: list[dict] = []
    failures: list[str] = []
    for check in CHECKS:
        text = check["path"].read_text(encoding="utf-8")
        needles = check["needles"]
        if check["name"] == "trade side sign maps sell to negative":
            needles = ['if raw in {"S", "SELL", "\u5356", "\u4e3b\u52a8\u5356", "2"}:', "return -1"]
        elif check["name"] == "capital model rule flow intention uses signed direction":
            needles = [
                '"rule_flow_signed_amount"',
                'intention = "\u4e70\u5165" if float(capital_source_debug["rule_flow_signed_amount"]) > 0 else "\u5356\u51fa"',
            ]
        missing = [needle for needle in needles if needle not in text]
        results.append(
            {
                "name": check["name"],
                "path": check["path"],
                "passed": not missing,
                "missing": missing,
            }
        )
        if missing:
            failures.append(check["name"])
    return results, failures


def render_report(results: list[dict], failures: list[str]) -> str:
    lines = [
        "# Sign Static Check Report",
        "",
        "## Contract",
        "",
        "- Official formula fields must use signed accumulation: buy is positive, sell is negative.",
        "- Official signed fields: `CH_rule_t`, `Q_rule_t`, `R_seed_t`, `signed_large_active_amount`, `signed_mix_qr_amount`, `signed_amount`.",
        "- Gross display fields may remain non-negative and must not be treated as the formula source of truth.",
        "",
        "## Results",
        "",
    ]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        rel_path = result["path"].relative_to(ROOT)
        lines.append(f"- `{status}` {result['name']} ({rel_path})")
        for missing in result["missing"]:
            lines.append(f"  - missing: `{missing}`")

    lines.extend(
        [
            "",
            "## Gross Display Fields",
            "",
            "These fields are intentionally gross/display counters and can be positive for sell-side volume:",
            "",
        ]
    )
    lines.extend(f"- `{field}`" for field in GROSS_FIELD_NOTES)
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- total_checks: `{len(results)}`",
            f"- failed_checks: `{len(failures)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def test_static_sign_contract() -> None:
    results, failures = run_sign_contract_checks()
    REPORT_PATH.write_text(render_report(results, failures), encoding="utf-8")
    assert not failures, "Failed sign contract checks: " + ", ".join(failures)
