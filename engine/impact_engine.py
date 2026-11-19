
import json
import sys
from collections import deque
from pathlib import Path


def load_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def normalize(text):
    return " ".join((text or "").lower().split())


def find_component_mentions(text, components):
    normalized_text = normalize(text)
    matches = []

    for component in components:
        names = [
            component.get("name", ""),
            *component.get("aliases", [])
        ]

        for name in names:
            name = normalize(name)

            if not name or len(name) < 3:
                continue

            if name in normalized_text:
                matches.append(component)
                break

    return matches


def trace_impact(start_id, relationships, components_by_id):
    queue = deque([(start_id, 0, [start_id])])
    visited = {start_id}
    impacts = []

    while queue:
        current_id, depth, path = queue.popleft()

        if depth >= 10:
            continue

        for relationship in relationships:
            if relationship["source_id"] != current_id:
                continue

            target_id = relationship["target_id"]

            if target_id in visited:
                continue

            if target_id not in components_by_id:
                continue

            visited.add(target_id)
            next_path = path + [target_id]

            impacts.append({
                "component": components_by_id[target_id],
                "impact_type": (
                    "DIRECT" if depth == 0 else "INDIRECT"
                ),
                "distance": depth + 1,
                "relationship_type": relationship["type"],
                "relationship_description": relationship.get(
                    "description", ""
                ),
                "path": next_path
            })

            queue.append((target_id, depth + 1, next_path))

    return impacts


def analyze(requirements_data, knowledge):
    components = knowledge.get("components", [])
    relationships = knowledge.get("relationships", [])

    components_by_id = {
        component["id"]: component
        for component in components
    }

    results = []

    for finding in requirements_data.get("findings", []):
        text = finding.get("text", "")
        matched_components = find_component_mentions(
            text, components
        )

        matched_ids = {
            component["id"] for component in matched_components
        }

        impacts = []

        for component in matched_components:
            impacts.extend(
                trace_impact(
                    component["id"],
                    relationships,
                    components_by_id
                )
            )

        # Remove duplicate impact entries while preserving order.
        unique_impacts = []
        seen = set()

        for impact in impacts:
            component_id = impact["component"]["id"]

            if component_id in matched_ids or component_id in seen:
                continue

            seen.add(component_id)
            unique_impacts.append(impact)

        results.append({
            "requirement_id": finding.get("id"),
            "requirement_text": text,
            "matched_components": [
                {
                    "id": component["id"],
                    "name": component["name"],
                    "type": component["type"]
                }
                for component in matched_components
            ],
            "impacted_components": [
                {
                    "id": item["component"]["id"],
                    "name": item["component"]["name"],
                    "type": item["component"]["type"],
                    "impact_type": item["impact_type"],
                    "distance": item["distance"],
                    "relationship": item["relationship_type"],
                    "reason": item["relationship_description"],
                    "path": item["path"]
                }
                for item in unique_impacts
            ],
            "analysis_status": (
                "MATCH_FOUND" if matched_components
                else "NO_EXACT_COMPONENT_MATCH"
            ),
            "review_required": True
        })

    return {
        "repository": knowledge.get("repository_name"),
        "environment": knowledge.get("environment", "UNKNOWN"),
        "analysis_method": "Exact-name matching and relationship traversal",
        "result_count": len(results),
        "results": results,
        "limitations": [
            "Only explicit component names and aliases are matched.",
            "Relationship direction follows the source-to-target definition.",
            "Missing relationships cannot be discovered automatically.",
            "Results require human validation and are not production decisions."
        ]
    }


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python impact_engine.py "
            "<analysis.json> <system_knowledge.json>"
        )
        sys.exit(1)

    try:
        requirements_data = load_json(sys.argv[1])
        knowledge = load_json(sys.argv[2])

        output = analyze(requirements_data, knowledge)

        output_path = Path("impact_analysis_results.json")
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print("Impact analysis completed.")
        print(f"Requirements analyzed: {output['result_count']}")
        print(f"Output file: {output_path}")

        for result in output["results"]:
            print(f"\n{result['requirement_id']}:")
            print(f"Requirement: {result['requirement_text']}")

            print(
                "Matched components:",
                ", ".join(
                    item["name"]
                    for item in result["matched_components"]
                ) or "None"
            )

            for item in result["impacted_components"]:
                print(
                    f"  {item['impact_type']}: {item['name']} "
                    f"(distance={item['distance']})"
                )
                print(f"    Reason: {item['reason']}")

    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"Impact analysis failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
