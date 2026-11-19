
import json
import re
import sys
from pathlib import Path

from docx import Document


def clean_text(value):
    """Normalize whitespace while preserving readable content."""
    return re.sub(r"\s+", " ", value or "").strip()


def read_brd(file_path):
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() != ".docx":
        raise ValueError("Please provide a Word .docx file.")

    document = Document(path)

    sections = []
    tables = []

    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = clean_text(paragraph.text)

        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style else "Normal"

        sections.append({
            "paragraph_number": index,
            "style": style_name,
            "text": text
        })

    for table_number, table in enumerate(document.tables, start=1):
        rows = []

        for row_number, row in enumerate(table.rows, start=1):
            cells = [clean_text(cell.text) for cell in row.cells]

            rows.append({
                "row_number": row_number,
                "cells": cells
            })

        tables.append({
            "table_number": table_number,
            "rows": rows
        })

    return {
        "source_file": path.name,
        "paragraph_count": len(sections),
        "table_count": len(tables),
        "paragraphs": sections,
        "tables": tables
    }


def main():
    if len(sys.argv) < 2:
        print(
            'Usage: python brd_reader.py "C:\\path\\to\\document.docx"'
        )
        sys.exit(1)

    input_path = Path(sys.argv[1])

    try:
        result = read_brd(input_path)

        output_path = input_path.with_name(
            f"{input_path.stem}_extracted.json"
        )

        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print("BRD extraction completed successfully.")
        print(f"Paragraphs extracted: {result['paragraph_count']}")
        print(f"Tables extracted: {result['table_count']}")
        print(f"Output file: {output_path}")

    except Exception as error:
        print(f"BRD extraction failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
