"""Local document extraction, candidate requirement analysis and explainable graph tracing."""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from collections import deque, defaultdict

SUPPORTED = {".docx", ".txt", ".md", ".json"}
ACTION_RE = re.compile(r"\b(must|shall|required to|needs to|should|will|validate|verify|ensure|prevent|allow|support|provide|enable|add|update|modify|remove|integrate|display|store|send|receive|calculate|generate)\b", re.I)
CHANGE_RE = re.compile(r"\b(add|update|modify|change|remove|replace|introduce|enhance|migrate|integrate|extend|new|改|تعديل|إضافة)\b", re.I)
RULE_RE = re.compile(r"\b(if|when|unless|before|after|only|must not|shall not|greater than|less than|within|at least|maximum|minimum)\b", re.I)
HEADING_RE = re.compile(r"^(executive summary|business requirements?|functional requirements?|data entities|interfaces|security requirements?|acceptance criteria|scope|requirements?)$", re.I)

def read_document(path: str | Path) -> dict:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported file type {ext or '(no extension)'}. Supported: {', '.join(sorted(SUPPORTED))}")
    items = []
    if ext == ".docx":
        try:
            from docx import Document
        except ImportError as e:
            raise RuntimeError("python-docx is required. Run: python -m pip install -r requirements.txt") from e
        doc = Document(path)
        # Preserve approximate document order by walking the XML body.
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        body = doc.element.body
        pnum = tnum = 0
        for child in body.iterchildren():
            if child.tag.endswith("}p"):
                pnum += 1
                p = Paragraph(child, doc)
                text = p.text.strip()
                if text:
                    items.append({"kind":"paragraph","source":f"Paragraph {pnum}","text":text,"style":p.style.name if p.style else ""})
            elif child.tag.endswith("}tbl"):
                tnum += 1
                table = Table(child, doc)
                for ri, row in enumerate(table.rows, 1):
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        items.append({"kind":"table_row","source":f"Table {tnum}, Row {ri}","table":tnum,"row":ri,"cells":cells,"text":" | ".join(cells)})
        for si, section in enumerate(doc.sections, 1):
            for label, part in (("header", section.header), ("footer", section.footer)):
                for pi, p in enumerate(part.paragraphs, 1):
                    if p.text.strip():
                        items.append({"kind":label,"source":f"Section {si} {label} paragraph {pi}","text":p.text.strip()})
    else:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        if ext == ".json":
            try: parsed = json.loads(raw)
            except json.JSONDecodeError: parsed = None
            if parsed is not None:
                raw = json.dumps(parsed, ensure_ascii=False, indent=2)
        for i, line in enumerate(raw.splitlines(), 1):
            if line.strip():
                items.append({"kind":"text","source":f"Line {i}","text":line.strip()})
    text = "\n".join(i["text"] for i in items)
    return {"file_name":path.name,"file_type":ext,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "item_count":len(items),"items":items,"text_characters":len(text),
            "limitations":["Images, text boxes and tracked-change markup may not be extracted." if ext==".docx" else "Plain-text line locations are retained."]}

def analyze_requirements(document: dict) -> dict:
    findings = []
    for item in document["items"]:
        text = item["text"].strip()
        if item["kind"] in ("header","footer") or len(text) < 12:
            continue
        if item["kind"] == "table_row":
            cells = item.get("cells", [])
            if cells and re.fullmatch(r"(id|requirement|description|priority|no\.?|#)", cells[0].strip(), re.I):
                continue
            req_id = next((c for c in cells if re.fullmatch(r"(REQ|BR|FR|NFR)[-_ ]?\d+", c.strip(), re.I)), None)
            content_cells = [c for c in cells if c and c != req_id and not re.fullmatch(r"(high|medium|low|critical|must|should|could)", c.strip(), re.I)]
            content = " | ".join(content_cells) if content_cells else text
        else:
            content, req_id = text, None
        if HEADING_RE.match(content.strip(" :#")):
            continue
        action = bool(ACTION_RE.search(content))
        rule = bool(RULE_RE.search(content))
        change = bool(CHANGE_RE.search(content))
        has_req_id = bool(req_id)
        candidate = action or has_req_id or (item["kind"] == "table_row" and change)
        if not candidate:
            continue
        flags = []
        if action: flags.append("action_or_obligation_language")
        if rule: flags.append("conditional_or_constraint_language")
        if change: flags.append("change_language")
        if has_req_id: flags.append("explicit_requirement_id")
        # Sample/template noise detection is intentionally conservative and visible.
        boilerplate = bool(re.search(r"\b(lorem ipsum|sample requirement|test content|all values are fictional)\b", content, re.I))
        if boilerplate: flags.append("template_or_placeholder_text")
        confidence = 0.28 + 0.22*bool(has_req_id) + 0.18*bool(action) + 0.12*bool(rule) + 0.12*bool(change)
        if boilerplate: confidence = min(confidence, 0.15)
        kind = "change_request" if change and not rule else ("business_rule_candidate" if rule else "requirement_candidate")
        findings.append({
            "id": req_id or f"CAND-{len(findings)+1:03d}", "source":item["source"], "kind":kind,
            "text":content, "original_row":item.get("cells"), "priority":next((c for c in (item.get("cells") or []) if c.lower() in ("critical","high","medium","low")),None),
            "candidate":candidate, "flags":flags, "confidence":round(confidence,2),
            "review_status":"needs_human_review", "placeholder_warning":boilerplate
        })
    full_text = "\n".join(x["text"] for x in document["items"])
    placeholder = bool(re.search(r"\b(lorem ipsum|sample requirement|test content)\b", full_text, re.I))
    return {"document":document["file_name"],"sha256":document["sha256"],"findings":findings,
            "finding_count":len(findings),"placeholder_content_detected":placeholder,
            "quality_note":"Candidate extraction is heuristic; review every finding and source excerpt."}

def _norm(s):
    s = s.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", s).strip()

def match_components(text: str, components: list[dict]) -> list[dict]:
    norm_text = f" {_norm(text)} "
    tokens = set(norm_text.split())
    matches = []
    for c in components:
        terms = [c.get("name","")] + c.get("aliases",[])
        best = None
        for term in terms:
            nt = _norm(term)
            if not nt: continue
            if f" {nt} " in norm_text:
                score, evidence = 0.94 if nt == _norm(c.get("name","")) else 0.88, term
                if best is None or score > best["confidence"]:
                    best = {"confidence":score,"matched_term":term,"match_type":"exact_normalized_phrase","evidence":f"Text contains component name/alias: '{term}'"}
            else:
                tt = set(nt.split())
                overlap = len(tt & tokens)/max(1,len(tt))
                if len(tt) >= 2 and overlap >= 0.75 and (best is None or overlap*0.65 > best["confidence"]):
                    best = {"confidence":round(overlap*0.65,2),"matched_term":term,"match_type":"token_overlap","evidence":f"Token overlap for alias/name '{term}'"}
        if best:
            matches.append({"component_id":c["id"],"component_name":c["name"],"component_type":c.get("type","unknown"),**best,
                            "review_required":best["confidence"] < 0.9})
    return sorted(matches,key=lambda x:x["confidence"],reverse=True)

def trace_impacts(analysis: dict, repository: dict, threshold: float = 0.65) -> dict:
    components = repository.get("components", [])
    by_id = {c["id"]:c for c in components}
    adjacency = defaultdict(list)
    warnings = []
    for rel in repository.get("relationships", []):
        if rel.get("direction","source_to_target") != "source_to_target":
            warnings.append(f"Relationship {rel.get('source')}->{rel.get('target')} skipped: unsupported direction.")
            continue
        if rel.get("source") not in by_id or rel.get("target") not in by_id:
            warnings.append(f"Relationship references unknown component: {rel}")
            continue
        if rel.get("propagate_impact") is True:
            adjacency[rel["source"]].append(rel)
    results = []
    for finding in analysis.get("findings", []):
        matches = match_components(finding["text"], components)
        eligible = [m for m in matches if m["confidence"] >= threshold]
        impacts, seen = [], set()
        for m in eligible:
            start = m["component_id"]
            queue = deque([(start,0,[start],[])])
            visited_dist = {start:0}
            while queue:
                cid, dist, path, relpath = queue.popleft()
                if dist and cid not in seen:
                    c = by_id[cid]
                    impacts.append({"component_id":cid,"component_name":c["name"],"component_type":c.get("type","unknown"),
                                    "impact_type":"direct" if dist==1 else "indirect","distance":dist,
                                    "path":[by_id[x]["name"] for x in path],
                                    "relationships":[r.get("type","DEPENDS_ON") for r in relpath],
                                    "relationship_evidence":[r.get("source_evidence","not supplied") for r in relpath],
                                    "status":"candidate_impact_requires_validation"})
                    seen.add(cid)
                for rel in adjacency.get(cid,[]):
                    nxt=rel["target"]
                    if nxt not in path and (nxt not in visited_dist or dist+1 < visited_dist[nxt]):
                        visited_dist[nxt]=dist+1
                        queue.append((nxt,dist+1,path+[nxt],relpath+[rel]))
        results.append({"finding_id":finding["id"],"source":finding["source"],"finding_text":finding["text"],
                        "matches":matches,"matched_components":[m["component_name"] for m in eligible],
                        "unmatched_or_uncertain":not bool(eligible),"candidate_impacts":impacts,
                        "review_required":True})
    return {"repository":repository.get("system",{}),"repository_is_synthetic":repository.get("system",{}).get("synthetic",False),
            "semantics":"Only relationships with propagate_impact=true are traversed, source -> target. These are candidate graph paths, not confirmed production impacts.",
            "results":results,"warnings":warnings}

def run_pipeline(paths: list[str], repo_path: str | Path) -> dict:
    repo = json.loads(Path(repo_path).read_text(encoding="utf-8"))
    docs = []
    for p in paths:
        doc = read_document(p)
        analysis = analyze_requirements(doc)
        impacts = trace_impacts(analysis, repo)
        docs.append({"extraction":doc,"analysis":analysis,"impact_analysis":impacts})
    return {"application":"NASJ Impact Analyzer","version":"0.2.0","documents":docs}
