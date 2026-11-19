"""Impact Analyzer — Evidence-Driven NLP Matching & Multi-Factor Impact Strategy Engine."""
from __future__ import annotations

import io
import json
import re
import tempfile
from collections import deque
from pathlib import Path

try:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except Exception:
    Document = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

SUPPORTED = {".docx", ".pdf", ".txt", ".md", ".json"}

REQ_WORDS = (
    "يجب", "يلزم", "يتعين", "ينبغي", "لا بد", "مطلوب",
    "shall", "must", "should", "required to", "needs to", "will", "req-", "fr-", "br-"
)
RULE_WORDS = (
    "إذا", "عندما", "في حال", "منع", "التحقق", "شرط", "قاعدة", "قبل", "بعد", "إلزامي",
    "if", "when", "unless", "only if", "validate", "validation", "rule", "must not", "shall not", "before", "mandatory"
)
RISK_WORDS = (
    "حساس", "فشل", "مخاطر", "خطر", "مهلة", "صلاحية", "غير مخول", "تكرار", "حرجة", "مرتفعة", "إيقاف", "تأخير", "رفض",
    "timeout", "failure", "risk", "critical", "high", "unauthorized", "duplicate", "latency", "block", "sla", "reject"
)

DOMAIN_TRIGGERS = {
    "validation_security": (
        "تحقق", "صحة", "رفض", "منع", "إلزامي", "موافقة", "مهلة", "صلاحية", "حساس",
        "validate", "validation", "block", "reject", "mandatory", "approval", "timeout", "sla", "security"
    ),
    "risk_selectivity": (
        "مخاطر", "انتقائية", "تفتيش", "معاينة", "مسار", "أحمر", "أصفر", "تقييم المخاطر",
        "risk", "selectivity", "inspection", "lane", "routing", "screening"
    ),
    "financial_tariff": (
        "تعرفة", "قيمة", "رسوم", "دفع", "مدفوعات", "سداد", "إعفاء", "ضريبة", "بند جمركي",
        "tariff", "valuation", "payment", "fee", "duty", "exemption", "hs code", "cif", "fob"
    ),
    "analytics_reporting": (
        "تقرير", "تقارير", "مؤشر", "مؤشرات", "لوحة", "إحصائية", "تدقيق", "أرشفة",
        "report", "reporting", "kpi", "dashboard", "analytics", "bi", "audit", "archive"
    ),
}

MODULE_DOMAIN_MAP = {
    "MOD-02": "validation_security",
    "MOD-13": "validation_security",
    "MOD-06": "risk_selectivity",
    "MOD-07": "risk_selectivity",
    "MOD-08": "risk_selectivity",
    "MOD-04": "financial_tariff",
    "MOD-05": "financial_tariff",
    "MOD-09": "financial_tariff",
    "MOD-14": "analytics_reporting",
    "MOD-15": "analytics_reporting",
}

OUT_OF_SCOPE_RE = re.compile(r"(خارج النطاق|مستبعد|لا يشمل|out of scope|excluded from scope|not in scope)", re.I)
HEADER_CELL_RE = re.compile(
    r"^(id|req|requirement|description|priority|no\.?|#|version|date|author|status|title|"
    r"الرقم|المعرف|المتطلب|الوصف|الأولوية|الإصدار|التاريخ|المؤلف|الحالة|البند|م)$",
    re.I,
)
META_TABLE_RE = re.compile(r"^(version|revision|document owner|prepared by|approved by|إصدار|مراجعة|إعداد|اعتماد)\b", re.I)
REQ_ID_RE = re.compile(r"\b((?:REQ|BR|FR|NFR|CR)[-_ ]?\d{1,4})\b", re.I)


def norm_text(s: str) -> str:
    """Normalize Arabic and English text for accurate phrase and morphological matching."""
    s = (s or "").casefold()
    s = re.sub(r"[ًٌٍَُِّْـ]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    s = s.replace("&", " and ")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", s).strip()


def _strip_ar_prefixes(token: str) -> set[str]:
    """Generate stem candidates by stripping common Arabic attached proclitics."""
    variants = {token}
    if not re.search(r"[\u0600-\u06ff]", token) or len(token) < 4:
        return variants
    for p in ("لل", "وال", "فال", "بال", "كال", "ال", "و", "ف", "ب", "ك", "ل"):
        if token.startswith(p) and len(token) - len(p) >= 3:
            v = token[len(p):]
            variants.add(v)
            if v.startswith("ال") and len(v) > 4:
                variants.add(v[2:])
    return variants


def _token_phrase_match(norm_doc: str, norm_alias: str) -> bool:
    """Match normalized alias cleanly on word boundaries, including Arabic proclitic variants."""
    if not norm_alias or len(norm_alias) < 3:
        return False
    if f" {norm_alias} " in f" {norm_doc} ":
        return True
    alias_tokens = norm_alias.split()
    doc_tokens = norm_doc.split()
    if not alias_tokens or not doc_tokens:
        return False
    doc_variants = [_strip_ar_prefixes(t) for t in doc_tokens]
    alias_variants = [_strip_ar_prefixes(t) for t in alias_tokens]
    n_a = len(alias_variants)
    for idx in range(len(doc_variants) - n_a + 1):
        if all(bool(doc_variants[idx + k] & alias_variants[k]) for k in range(n_a)):
            return True
    return False


def _clean_table_row(cells: list[str]) -> tuple[str, list[str]]:
    """Deduplicate merged-cell repeats and produce clean prose instead of raw '|' pipes."""
    deduped = []
    for c in cells:
        clean_c = re.sub(r"\s+", " ", c).strip()
        if clean_c and (not deduped or deduped[-1] != clean_c):
            deduped.append(clean_c)
    if not deduped:
        return "", []
    if len(deduped) >= 2 and REQ_ID_RE.fullmatch(deduped[0]):
        head = deduped[0].upper().replace(" ", "-")
        body = " — ".join(deduped[1:])
        return f"{head}: {body}", deduped
    return " — ".join(deduped), deduped


def extract_bytes(filename: str, raw: bytes) -> list[dict]:
    """Extract ordered paragraphs and structured table rows from DOCX, PDF, TXT, MD, or JSON bytes."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"نوع ملف غير مدعوم ({ext}). الأنواع المدعومة: DOCX, PDF, TXT, MD, JSON")

    if ext == ".docx":
        if Document is None:
            raise ValueError("مكتبة python-docx غير مثبتة؛ نفّذ pip install -r requirements.txt")
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(raw)
            tmp_path = Path(f.name)
        try:
            doc = Document(str(tmp_path))
            out = []
            pnum = tnum = 0
            for child in doc.element.body.iterchildren():
                if child.tag.endswith("}p"):
                    pnum += 1
                    txt = re.sub(r"\s+", " ", Paragraph(child, doc).text).strip()
                    if txt:
                        out.append({"source": f"فقرة {pnum}", "kind": "paragraph", "text": txt, "cells": []})
                elif child.tag.endswith("}tbl"):
                    tnum += 1
                    tbl = Table(child, doc)
                    for ri, row in enumerate(tbl.rows, 1):
                        vals = [c.text.strip().replace("\n", " ") for c in row.cells]
                        non_empty = [v for v in vals if v]
                        if not non_empty:
                            continue
                        if ri == 1 and all(HEADER_CELL_RE.match(v) for v in non_empty[:3]):
                            continue
                        if META_TABLE_RE.match(non_empty[0]) and len(" ".join(non_empty)) < 90:
                            continue
                        txt, cells = _clean_table_row(non_empty)
                        if txt:
                            out.append({
                                "source": f"جدول {tnum} · صف {ri}",
                                "kind": "table_row",
                                "text": txt,
                                "cells": cells,
                            })
            return out
        finally:
            tmp_path.unlink(missing_ok=True)

    if ext == ".pdf":
        if PdfReader is None:
            raise ValueError("قراءة PDF تتطلب تثبيت pypdf؛ نفّذ pip install -r requirements.txt")
        reader = PdfReader(io.BytesIO(raw))
        out = []
        for i, page in enumerate(reader.pages, 1):
            txt = (page.extract_text() or "").strip()
            if txt:
                for li, line in enumerate(txt.splitlines(), 1):
                    clean_l = re.sub(r"\s+", " ", line).strip()
                    if clean_l:
                        out.append({"source": f"صفحة {i} · سطر {li}", "kind": "pdf_line", "text": clean_l, "cells": []})
        if not out:
            raise ValueError("لم يتم استخراج نص من ملف PDF؛ قد يكون ممسوحًا ضوئيًا.")
        return out

    if ext in (".txt", ".md"):
        lines = raw.decode("utf-8-sig", errors="replace").splitlines()
        return [
            {"source": f"سطر {i}", "kind": "text", "text": re.sub(r"\s+", " ", line).strip(), "cells": []}
            for i, line in enumerate(lines, 1)
            if line.strip()
        ]

    obj = json.loads(raw.decode("utf-8-sig"))
    arr = obj if isinstance(obj, list) else [obj]
    return [
        {
            "source": f"عنصر {i}",
            "kind": "json",
            "text": json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x),
            "cells": [],
        }
        for i, x in enumerate(arr, 1)
    ]


def _normalize_repo(repo: dict) -> tuple[dict[str, dict], list[dict]]:
    """Support both v9/v13 (from/to/propagation) and v0.2 (source/target/propagate_impact) schemas."""
    by_id = {c["id"]: c for c in repo.get("components", [])}
    rels = []
    for r in repo.get("relationships", []):
        src = r.get("from") or r.get("source") or r.get("source_id")
        dst = r.get("to") or r.get("target") or r.get("target_id")
        prop = r.get("propagation") if "propagation" in r else r.get("propagate_impact", True)
        if src in by_id and dst in by_id and prop is not False:
            rels.append({
                "from": src,
                "to": dst,
                "type": r.get("type", "DEPENDS_ON"),
                "verb_en": r.get("verb_en", "CALLS"),
                "label": r.get("label", r.get("type", "يعتمد على")),
                "coupling": r.get("coupling", "data_dependency"),
                "base_weight": int(r.get("base_weight", 2)),
                "strategy_note": r.get("strategy_note", ""),
                "evidence": r.get("evidence") or r.get("source_evidence") or "علاقة معرفة في مستودع النظام"
            })
    return by_id, rels


def _evaluate_edge_strategy(
    rel: dict,
    target_comp: dict,
    distance: int,
    matched_ids: set[str],
    active_domains: set[str],
    has_risk: bool,
    has_rule: bool,
    out_of_scope: bool,
) -> dict:
    """
    Real Multi-Factor Impact Strategy Evaluation:
    Computes severity ('critical' | 'moderate' | 'low' | 'unaffected'), numeric risk score,
    strategic rationale in Arabic + English, and required engineering action.
    """
    if out_of_scope:
        return {
            "severity": "unaffected",
            "severity_ar": "غير متأثر (خارج النطاق)",
            "severity_en": "Unaffected",
            "score": 0,
            "rationale": "البند مصنّف خارج نطاق التنفيذ؛ لا ينتقل الأثر عبر هذا المسار.",
            "action": "لا يلزم إجراء"
        }

    tid = target_comp["id"]
    ctype = target_comp.get("type", "service")
    coupling = rel.get("coupling", "data_dependency")
    score = int(rel.get("base_weight", 2))
    reasons = []

    if rel.get("strategy_note"):
        reasons.append(rel["strategy_note"])

    mod_domain = MODULE_DOMAIN_MAP.get(tid)
    if tid in matched_ids:
        score += 2
        reasons.append("الوحدة مذكورة صراحةً في نص المتطلب")
    elif mod_domain and mod_domain in active_domains:
        score += 2
        reasons.append("تطابق مباشر مع مجال التغيير في المتطلب")

    if has_risk and (coupling == "synchronous_blocking" or ctype in ("rules_engine", "workflow", "integration")):
        score += 1
        reasons.append("وجود مؤشرات مخاطر/مهلة زمنية على مسار تشغيلي")
    if has_rule and ctype in ("rules_engine", "service") and coupling == "synchronous_blocking":
        score += 1
        reasons.append("قاعدة أعمال إلزامية تؤثر على منطق التحقق أو التقييم")

    if ctype == "analytics" or rel.get("type") in ("FEEDS_REPORTING", "AUDITED_AFTER_CLEARANCE"):
        if "analytics_reporting" not in active_domains and tid not in matched_ids:
            score = min(score, 1)
            reasons.append("تغذية تحليلية/رقابية غير معطّلة لسير التخليص")
        else:
            score = min(score, 2)
            reasons.append("تحديث مطلوب في نماذج التقارير ولوحات المؤشرات")

    if distance == 2:
        score -= 1
        reasons.append("تضاؤل الأثر عند القفزة الثانية (Hop 2)")
    elif distance >= 3:
        score -= 2
        reasons.append(f"أثر تتابعي بعيد (Hop {distance}) — تبعية غير مباشرة منخفضة")

    score = max(1, min(5, score))

    if score >= 4:
        return {
            "severity": "critical",
            "severity_ar": "حرج · عالي الخطورة",
            "severity_en": "Critical",
            "score": score,
            "rationale": " ؛ ".join(reasons),
            "action": "اختبار انحدار إلزامي + اعتماد عقد API/قواعد الأعمال"
        }
    if score >= 2:
        return {
            "severity": "moderate",
            "severity_ar": "متوسط · تشغيلي",
            "severity_en": "Moderate",
            "score": score,
            "rationale": " ؛ ".join(reasons),
            "action": "مراجعة مطابقة الحقول واختبار سيناريو UAT"
        }
    return {
        "severity": "low",
        "severity_ar": "منخفض · معلوماتي",
        "severity_en": "Low",
        "score": score,
        "rationale": " ؛ ".join(reasons),
        "action": "مراقبة تحديث البيانات / تقارير BI فقط"
    }


def analyze_parts(parts: list[dict], repo: dict) -> list[dict]:
    by_id, rels = _normalize_repo(repo)
    comps = list(by_id.values())
    findings = []

    for idx, part in enumerate(parts, 1):
        txt = part["text"].strip()
        if len(txt) < 10:
            continue
        low = txt.lower()
        n_txt = norm_text(txt)
        out_of_scope = bool(OUT_OF_SCOPE_RE.search(txt))

        explicit_id_m = REQ_ID_RE.search(txt)
        item_id = explicit_id_m.group(1).upper().replace(" ", "-") if explicit_id_m else f"REQ-{len(findings) + 1:03d}"

        is_req = (not out_of_scope) and any(w in low for w in REQ_WORDS)
        is_rule = (not out_of_scope) and any(w in low for w in RULE_WORDS)
        risk_hits = [w for w in RISK_WORDS if w in low]

        active_domains = set()
        for dom_key, kws in DOMAIN_TRIGGERS.items():
            if any(kw in low for kw in kws):
                active_domains.add(dom_key)

        matched_components = []
        matched_ids = set()
        for c in comps:
            candidates = [c.get("name", ""), c.get("name_ar", "")] + c.get("aliases", [])
            best_ev = None
            best_score = 0
            for alias in candidates:
                na = norm_text(alias)
                if _token_phrase_match(n_txt, na):
                    is_exact_name = na in (norm_text(c.get("name", "")), norm_text(c.get("name_ar", "")))
                    score = 96 if is_exact_name else 88
                    if score > best_score:
                        best_score = score
                        best_ev = alias
            if best_ev:
                matched_ids.add(c["id"])
                matched_components.append({
                    "id": c["id"],
                    "name": c["name"],
                    "name_ar": c.get("name_ar", c["name"]),
                    "type": c.get("type", "service"),
                    "api_component": c.get("api_component", f"{c['name']} API"),
                    "database_asset": c.get("database_asset", f"{c['id']}_DB"),
                    "powerbi_report": c.get("powerbi_report", "Customs Reporting"),
                    "evidence": best_ev,
                    "confidence_pct": best_score,
                    "confidence": "مرتفع" if best_score >= 90 else "متوسط"
                })

        if not (explicit_id_m or is_req or is_rule or risk_hits or matched_components):
            continue

        graph_edges = []
        seen_edges = set()
        best_impact_by_target: dict[str, dict] = {}

        for mc in matched_components:
            start = mc["id"]
            queue = deque([(start, 0, [start])])
            visited_dist = {start: 0}
            while queue:
                curr, dist, path = queue.popleft()
                if dist >= 5:
                    continue
                for rel in rels:
                    if rel["from"] != curr:
                        continue
                    nxt = rel["to"]
                    if nxt in path:
                        continue
                    new_dist = dist + 1
                    target_comp = by_id[nxt]
                    strat = _evaluate_edge_strategy(
                        rel=rel,
                        target_comp=target_comp,
                        distance=new_dist,
                        matched_ids=matched_ids,
                        active_domains=active_domains,
                        has_risk=bool(risk_hits),
                        has_rule=is_rule,
                        out_of_scope=out_of_scope,
                    )
                    edge_key = (curr, nxt, rel["type"])
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        graph_edges.append({
                            "from": curr,
                            "to": nxt,
                            "type": rel["type"],
                            "verb_en": rel["verb_en"],
                            "label": rel["label"],
                            "kind": "مباشر" if new_dist == 1 else "غير مباشر",
                            "severity": strat["severity"],
                            "severity_ar": strat["severity_ar"],
                            "severity_en": strat["severity_en"],
                            "strategy_score": strat["score"],
                            "strategy_rationale": strat["rationale"],
                            "recommended_action": strat["action"],
                        })
                    if nxt not in matched_ids:
                        entry = {
                            "component_id": nxt,
                            "component": target_comp["name"],
                            "component_ar": target_comp.get("name_ar", target_comp["name"]),
                            "component_type": target_comp.get("type", "service"),
                            "api_component": target_comp.get("api_component", ""),
                            "database_asset": target_comp.get("database_asset", ""),
                            "powerbi_report": target_comp.get("powerbi_report", ""),
                            "distance": new_dist,
                            "kind": "مباشر" if new_dist == 1 else "غير مباشر",
                            "severity": strat["severity"],
                            "severity_ar": strat["severity_ar"],
                            "severity_en": strat["severity_en"],
                            "strategy_score": strat["score"],
                            "strategy_rationale": strat["rationale"],
                            "recommended_action": strat["action"],
                            "relationship": rel["label"],
                            "verb_en": rel["verb_en"],
                            "reason": strat["rationale"],
                            "path_ids": path + [nxt],
                            "path": [by_id[k]["name"] for k in (path + [nxt])],
                            "path_ar": [by_id[k].get("name_ar", by_id[k]["name"]) for k in (path + [nxt])]
                        }
                        prev = best_impact_by_target.get(nxt)
                        if prev is None or new_dist < prev["distance"] or (new_dist == prev["distance"] and strat["score"] > prev["strategy_score"]):
                            best_impact_by_target[nxt] = entry
                    if nxt not in visited_dist or new_dist < visited_dist[nxt]:
                        visited_dist[nxt] = new_dist
                        queue.append((nxt, new_dist, path + [nxt]))

        unaffected_boundaries = []
        seen_boundaries = set()
        involved_so_far = matched_ids | set(best_impact_by_target.keys())
        for mc in matched_components[:1]:
            core_id = mc["id"]
            for rel in rels:
                if rel["to"] == core_id and rel["from"] not in involved_so_far and rel["from"] not in seen_boundaries:
                    seen_boundaries.add(rel["from"])
                    up_comp = by_id[rel["from"]]
                    unaffected_boundaries.append({
                        "component_id": up_comp["id"],
                        "component": up_comp["name"],
                        "component_ar": up_comp.get("name_ar", up_comp["name"]),
                        "target_id": core_id,
                        "verb_en": rel["verb_en"],
                        "relationship": rel["label"],
                        "severity": "unaffected",
                        "severity_ar": "غير متأثر · تغذية قبلية",
                        "severity_en": "Unaffected",
                        "strategy_score": 0,
                        "strategy_rationale": f"وحدة تغذية قبلية ({rel['label']}) تسبق نقطة التغيير ولا تتأثر عكسيًا بالتعديل.",
                        "recommended_action": "لا يلزم تعديل — ضمن الحدود الآمنة",
                        "api_component": up_comp.get("api_component", ""),
                        "database_asset": up_comp.get("database_asset", ""),
                        "powerbi_report": up_comp.get("powerbi_report", ""),
                    })

        sev_rank = {"critical": 0, "moderate": 1, "low": 2, "unaffected": 3}
        candidate_impacts = sorted(
            best_impact_by_target.values(),
            key=lambda x: (sev_rank.get(x["severity"], 9), x["distance"], x["component_id"])
        )

        traceability_rows = []
        uat_tests = []
        seen_uat = set()

        involved_ids = [m["id"] for m in matched_components] + [i["component_id"] for i in candidate_impacts]
        for cid in involved_ids:
            comp = by_id[cid]
            is_direct_match = cid in matched_ids
            imp_obj = best_impact_by_target.get(cid)
            sev_en = "Critical" if is_direct_match else (imp_obj["severity_en"] if imp_obj else "Low")
            sev_ar = "حرج (نقطة التغيير)" if is_direct_match else (imp_obj["severity_ar"] if imp_obj else "منخفض")
            conf_level = (
                "High" if is_direct_match else ("Medium" if imp_obj and imp_obj["distance"] == 1 else "Needs Review")
            )
            traceability_rows.append({
                "req_id": item_id,
                "module_id": cid,
                "module_en": comp["name"],
                "module_ar": comp.get("name_ar", comp["name"]),
                "api_component": comp.get("api_component", ""),
                "database_asset": comp.get("database_asset", ""),
                "powerbi_report": comp.get("powerbi_report", ""),
                "impact_scope": "Matched" if is_direct_match else ("Direct" if imp_obj and imp_obj["distance"] == 1 else "Indirect"),
                "severity": "critical" if is_direct_match else (imp_obj["severity"] if imp_obj else "low"),
                "severity_en": sev_en,
                "severity_ar": sev_ar,
                "strategy_rationale": "نقطة التغيير الأساسية في المتطلب" if is_direct_match else (imp_obj["strategy_rationale"] if imp_obj else ""),
                "confidence": conf_level
            })
            if cid not in seen_uat and comp.get("uat_scenario") and (is_direct_match or (imp_obj and imp_obj["severity"] in ("critical", "moderate"))):
                seen_uat.add(cid)
                uat_tests.append({
                    "test_id": f"TEST-{len(uat_tests) + 1:03d}",
                    "module_id": cid,
                    "module_name": comp["name"],
                    "severity": sev_en,
                    "title": comp["uat_scenario"]
                })

        findings.append({
            "id": item_id,
            "source": part["source"],
            "kind": part.get("kind", "paragraph"),
            "cells": part.get("cells", []),
            "text": txt,
            "requirement_candidate": is_req,
            "business_rule_candidate": is_rule,
            "out_of_scope": out_of_scope,
            "active_domains": sorted(active_domains),
            "risk_indicators": risk_hits,
            "matched_components": matched_components,
            "candidate_impacts": candidate_impacts,
            "unaffected_boundaries": unaffected_boundaries,
            "graph_edges": graph_edges,
            "traceability_rows": traceability_rows,
            "uat_tests": uat_tests,
            "review_status": "needs_human_review"
        })

    return findings


def analyze_uploaded_items(items: list[tuple], repo: dict) -> dict:
    all_parts = []
    docs = []
    for item in items:
        if len(item) == 3:
            role, name, raw = item
        else:
            name, raw = item
            role = "change"
        parts = extract_bytes(name, raw)
        role_label = "مستند التغيير" if role == "change" else "مستند مرجعي"
        docs.append({
            "filename": name,
            "role": role,
            "role_label": role_label,
            "extracted_items": len(parts),
            "format": Path(name).suffix.lower().lstrip(".")
        })
        for p in parts:
            all_parts.append({
                "source": f"{role_label} · {name} · {p['source']}",
                "kind": p.get("kind", "paragraph"),
                "cells": p.get("cells", []),
                "text": p["text"]
            })

    findings = analyze_parts(all_parts, repo)
    return {
        "documents": docs,
        "findings": findings,
        "strategy_model": "Multi-Factor Risk & Coupling Impact Strategy (Critical / Moderate / Low / Unaffected)",
        "repository_notice": "مستودع تجريبي اصطناعي؛ لا يمثل نظامًا حقيقيًا",
        "analysis_notice": "يتم تلوين المسارات وفق استراتيجية حقيقية تجمع بين نوع الاقتران البرمجي، نية المتطلب، وتضاؤل القفزات."
    }
