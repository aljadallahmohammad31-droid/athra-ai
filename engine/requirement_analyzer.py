
import json
import re
import sys
from pathlib import Path


REQUIREMENT_PATTERNS = [
    r"\bmust\b",
    r"\bshall\b",
    r"\bshould\b",
    r"\brequired to\b",
    r"\bsystem needs to\b",
    r"\bthe system needs to\b",
    r"\bneed to\b",
    r"\bلا بد\b",
    r"\bيجب\b",
    r"\bيتعين\b",
    r"\bينبغي\b",
]

RULE_PATTERNS = [
    r"\bif\b",
    r"\bwhen\b",
    r"\bonly if\b",
    r"\bunless\b",
    r"\bvalidate\b",
    r"\bvalidation\b",
    r"\bmust not\b",
    r"\bقبل\b",
    r"\bإذا\b",
    r"\bفي حال\b",
    r"\bالتحقق\b",
]

COMPONENT_PATTERNS = [
    "service",
    "interface",
    "api",
    "database",
    "table",
    "report",
    "dashboard",
    "job",
    "system",
    "declaration",
    "الخدمة",
    "الواجهة",
    "قاعدة البيانات",
    "التقرير",
    "النظام",
    "المعاملة",
]


def matches_any(text, patterns):
    text_lower = text.lower()
    return any(
        re.search(pattern, text_lower, re.IGNORECASE)
        for pattern in patterns
    )


def analyze_brd(source):
    findings = []
    requirement_number = 0

    for paragraph in source.get("paragraphs", []):
        text = paragraph.get("text", "").strip()

        if not text:
            continue

        is_requirement = matches_any(text, REQUIREMENT_PATTERNS)
        is_rule = matches_any(text, RULE_PATTERNS)

        if is_requirement or is_rule:
            requirement_number += 1

            findings.append({
                "id": f"REQ-{requirement_number:03d}",
                "source_type": "paragraph",
                "source_reference": (
                    f"Paragraph {paragraph.get('paragraph_number', '?')}"
                ),
                "text": text,
                "requirement_candidate": is_requirement,
                "business_rule_candidate": is_rule,
                "potential_components": [
                    term for term in COMPONENT_PATTERNS
                    if term.lower() in text.lower()
                ],
                "review_status": "NEEDS_HUMAN_REVIEW"
            })

    for table in source.get("tables", []):
        for row in table.get("rows", []):
            text = " | ".join(
                cell.strip()
                for cell in row.get("cells", [])
                if cell.strip()
            )

            if not text:
                continue

            is_requirement = matches_any(text, REQUIREMENT_PATTERNS)
            is_rule = matches_any(text, RULE_PATTERNS)

            if is_requirement or is_rule:
                requirement_number += 1

                findings.append({
                    "id": f"REQ-{requirement_number:03d}",
                    "source_type": "table",
                    "source_reference": (
                        f"Table {table.get('table_number', '?')}, "
                        f"Row {row.get('row_number', '?')}"
                    ),
                    "text": text,
                    "requirement_candidate": is_requirement,
                    "business_rule_candidate": is_rule,
                    "potential_components": [
                        term for term in COMPONENT_PATTERNS
                        if term.lower() in text.lower()
                    ],
                    "review_status": "NEEDS_HUMAN_REVIEW"
                })

    return {
        "source_file": source.get("source_file", "unknown"),
        "analysis_type": "rule_based_candidate_extraction",
        "finding_count": len(findings),
        "findings": findings,
        "limitations": [
            "This is rule-based extraction, not an AI model.",
            "Some requirements may be missed or incorrectly classified.",
            "Component mentions are candidates, not confirmed system impacts.",
            "Human review is required before using the results for decisions."
        ]
    }


def main():
    if len(sys.argv) != 2:
        print(
            'Usage: python requirement_analyzer.py '
            '"sample_brd_extracted.json"'
        )
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        sys.exit(1)

    try:
        source = json.loads(input_path.read_text(encoding="utf-8"))
        result = analyze_brd(source)

        output_path = input_path.with_name(
            f"{input_path.stem}_analysis.json"
        )

        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print("Requirement analysis completed.")
        print(f"Findings: {result['finding_count']}")
        print(f"Output file: {output_path}")

        for item in result["findings"]:
            print(
                f"\n{item['id']} | {item['source_reference']}\n"
                f"Text: {item['text']}\n"
                f"Requirement candidate: "
                f"{item['requirement_candidate']}\n"
                f"Business rule candidate: "
                f"{item['business_rule_candidate']}\n"
                f"Potential components: "
                f"{', '.join(item['potential_components']) or 'None'}"
            )

    except (OSError, json.JSONDecodeError, TypeError) as error:
        print(f"Analysis failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
