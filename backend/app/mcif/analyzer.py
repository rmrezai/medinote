from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


LAB_ALIASES = {
    "creatinine": "creatinine",
    "cr": "creatinine",
    "sodium": "sodium",
    "na": "sodium",
    "potassium": "potassium",
    "k": "potassium",
    "hemoglobin": "hemoglobin",
    "hgb": "hemoglobin",
    "hematocrit": "hematocrit",
    "hct": "hematocrit",
    "wbc": "wbc",
    "white blood cell": "wbc",
    "platelets": "platelets",
    "plt": "platelets",
    "glucose": "glucose",
    "bun": "bun",
}

LAB_UNITS = {
    "creatinine": "mg/dL",
    "sodium": "mmol/L",
    "potassium": "mmol/L",
    "hemoglobin": "g/dL",
    "hematocrit": "%",
    "wbc": "K/uL",
    "platelets": "K/uL",
    "glucose": "mg/dL",
    "bun": "mg/dL",
}

DIAGNOSIS_PATTERNS = [
    ("acute kidney injury", "acute_kidney_injury"),
    ("AKI", "acute_kidney_injury"),
    ("pneumonia", "pneumonia"),
    ("acute hypoxemic respiratory failure", "acute_hypoxemic_respiratory_failure"),
    ("acute hypoxic respiratory failure", "acute_hypoxemic_respiratory_failure"),
    ("heart failure", "heart_failure"),
    ("atrial fibrillation", "atrial_fibrillation"),
    ("GI bleed", "gastrointestinal_bleeding"),
    ("gastrointestinal bleed", "gastrointestinal_bleeding"),
    ("sepsis", "sepsis"),
    ("encephalopathy", "encephalopathy"),
]

MED_STATUS_PATTERNS = [
    (re.compile(r"\b(?P<med>[A-Za-z][A-Za-z0-9\-]{1,35})\s+(?:remains?|is|was)\s+held\b", re.I), "held"),
    (re.compile(r"\b(?:hold|held|holding)\s+(?P<med>[A-Za-z][A-Za-z0-9\- ]{1,45}?)(?=\s+(?:due to|for|because|given|$)|[.,;])", re.I), "held"),
    (re.compile(r"\b(?:resume|resumed|restart|restarted)\s+(?P<med>[A-Za-z][A-Za-z0-9\- ]{1,45}?)(?=\s+(?:due to|for|because|given|$)|[.,;])", re.I), "resumed"),
    (re.compile(r"\b(?:stop|stopped|discontinue|discontinued)\s+(?P<med>[A-Za-z][A-Za-z0-9\- ]{1,45}?)(?=\s+(?:due to|for|because|given|$)|[.,;])", re.I), "stopped"),
    (re.compile(r"\b(?:continue|continued)\s+(?P<med>[A-Za-z][A-Za-z0-9\- ]{1,45}?)(?=\s+(?:due to|for|because|given|$)|[.,;])", re.I), "ordered"),
]

PENDING_PATTERN = re.compile(r"\b(?P<item>(?:blood|urine|wound)?\s*cultures?|pathology|biopsy|MRI|CT|echo|echocardiogram)\s+(?:is|are|remains?|remain)?\s*pending\b", re.I)
CONSULT_PATTERN = re.compile(r"\b(?P<service>cardiology|nephrology|pulmonology|gastroenterology|GI|infectious disease|ID|neurology|surgery)\s+(?:recommends?|recommended|advises?|advised)\s+(?P<rec>[^.\n]+)", re.I)
OXYGEN_PATTERN = re.compile(r"(?:(?:now|currently)\s+)?(?:on\s+)?(?P<flow>\d+(?:\.\d+)?)\s*L(?:/min)?\s*(?:NC|nasal cannula)\b", re.I)
ROOM_AIR_PATTERN = re.compile(r"\b(?:on\s+)?room air\b", re.I)
HOME_MED_PATTERN = re.compile(r"\bhome medications?(?: include| are|:)?\s+(?P<meds>[^.\n]+)", re.I)
EXAM_PATTERN = re.compile(r"\b(?:focused\s+)?exam\s*:\s*(?P<exam>[^.\n]+)", re.I)
PT_RECOMMEND_PATTERN = re.compile(r"\bPT\s+recommends?\s+(?P<destination>[^.\n]+)", re.I)
OT_RECOMMEND_PATTERN = re.compile(r"\bOT\s+recommends?\s+(?P<destination>[^.\n]+)", re.I)
SLP_RECOMMEND_PATTERN = re.compile(r"\bSLP\s+recommends?\s+(?P<destination>[^.\n]+)", re.I)
DISCHARGE_PLAN_PATTERN = re.compile(r"\bdischarge plan(?: is)? documented as\s+(?P<destination>[^.\n]+)", re.I)
MOBILITY_PATTERN = re.compile(r"\bpatient\s+ambulates?\s+(?P<distance>\d+)\s*feet\s+with\s+(?P<detail>[^.\n]+)", re.I)
INPATIENT_NEED_PATTERN = re.compile(r"\brequires? inpatient (?:care|management) for\s+(?P<barriers>[^.\n]+)", re.I)
FINAL_RESULT_PATTERN = re.compile(r"\b(?P<item>(?:blood|urine|wound)?\s*cultures?|pathology|biopsy)\s+(?:is|are)?\s*(?:amended\s+)?final\s*:\s*(?P<result>[^.\n]+)", re.I)
PROCEDURE_PATTERN = re.compile(r"\b(?P<name>biopsy|bronchoscopy|colonoscopy|endoscopy|EGD|ERCP|thoracentesis|paracentesis|cardiac catheterization|heart catheterization)\s+(?:is|was)?\s*(?P<status>planned|pending|scheduled|cancelled|canceled|deferred|completed|performed)\b", re.I)


@dataclass
class CandidateFact:
    fact_type: str
    concept: str
    value_text: str | None = None
    value_numeric: float | None = None
    units: str | None = None
    evidence_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    observed_datetime: datetime | None = None
    fact_state: str = "current"
    confidence: str = "high"
    source_category: str = "clinician_documented"


@dataclass
class CandidateProblem:
    name: str
    normalized_name: str
    certainty: str = "confirmed"
    status: str = "active"
    evidence_text: str | None = None


@dataclass
class CandidateMedication:
    normalized_name: str
    display_name: str
    domain: str = "hospital"
    status: str = "ordered"
    reason: str | None = None
    evidence_text: str | None = None


@dataclass
class CandidateLab:
    test_name: str
    value_numeric: float | None = None
    value_text: str | None = None
    units: str | None = None
    evidence_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None


@dataclass
class CandidateVital:
    vital_type: str
    value_numeric: float | None = None
    value_text: str | None = None
    units: str | None = None
    oxygen_device: str | None = None
    oxygen_flow_lpm: float | None = None
    evidence_text: str | None = None


@dataclass
class CandidateConsult:
    service: str
    recommendation: str
    evidence_text: str


@dataclass
class CandidatePending:
    item_type: str
    description: str
    evidence_text: str


@dataclass
class CandidateDisposition:
    anticipated_destination: str | None = None
    current_barriers: list[str] = field(default_factory=list)
    mobility_status: str | None = None
    pt_recommendation: str | None = None
    ot_recommendation: str | None = None
    slp_recommendation: str | None = None
    oxygen_need: str | None = None
    evidence_text: str | None = None


@dataclass
class CandidateResolution:
    item_type: str
    description: str
    result_text: str
    evidence_text: str


@dataclass
class CandidateProcedure:
    procedure_name: str
    status: str
    evidence_text: str


@dataclass
class CandidateBundle:
    facts: list[CandidateFact] = field(default_factory=list)
    problems: list[CandidateProblem] = field(default_factory=list)
    medications: list[CandidateMedication] = field(default_factory=list)
    labs: list[CandidateLab] = field(default_factory=list)
    vitals: list[CandidateVital] = field(default_factory=list)
    consultants: list[CandidateConsult] = field(default_factory=list)
    pending_items: list[CandidatePending] = field(default_factory=list)
    dispositions: list[CandidateDisposition] = field(default_factory=list)
    resolved_items: list[CandidateResolution] = field(default_factory=list)
    procedures: list[CandidateProcedure] = field(default_factory=list)
    unresolved_text: list[str] = field(default_factory=list)


def _status_for(text: str, end: int) -> str:
    suffix = text[end:end + 60].lower()
    if re.match(r"\s+(?:is|are)?\s*improving\b", suffix):
        return "improving"
    if re.match(r"\s+(?:is|are)?\s*worsening\b", suffix):
        return "worsening"
    if re.match(r"\s+(?:is|are)?\s*stable\b", suffix):
        return "stable"
    if re.match(r"\s+(?:is|are)?\s*resolved\b", suffix):
        return "resolved"
    if re.match(r"\s+(?:is|are)?\s*(?:ruled out|not supported|removed)\b", suffix):
        return "resolved"
    return "active"


def _certainty_for(text: str, start: int) -> str:
    prefix = text[max(0, start - 45):start].lower()
    if re.search(r"(?:concern for|concerning for)\s*$", prefix):
        return "concern_for"
    if re.search(r"(?:possible|possibly)\s*$", prefix):
        return "possible"
    if re.search(r"(?:suspected|suspect)\s*$", prefix):
        return "suspected"
    if re.search(r"(?:probable|likely)\s*$", prefix):
        return "probable"
    return "confirmed"


def _normalize_med_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip(" .,:;\n\t")).strip()
    # Strip a trailing dose/frequency fragment so the same drug does not become
    # multiple medication identities (e.g. "losartan" vs "losartan 50 mg daily").
    name = re.sub(r"\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?|ml)\b.*$", "", name, flags=re.I).strip()
    return name.lower()


def _dedupe(items: Iterable, key):
    out = []
    seen = set()
    for item in items:
        marker = key(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def analyze_source_text(text: str, source_datetime: datetime | None = None, source_category: str = "clinician_documented") -> CandidateBundle:
    bundle = CandidateBundle()

    # High-confidence lab expressions such as "Cr 1.4", "creatinine: 2.1", "Hgb = 7.2".
    aliases = "|".join(sorted((re.escape(x) for x in LAB_ALIASES), key=len, reverse=True))
    lab_re = re.compile(rf"\b(?P<name>{aliases})\b\s*(?:[:=]|is|was|of)?\s*(?P<value>-?\d+(?:\.\d+)?)\b", re.I)
    for match in lab_re.finditer(text):
        alias = match.group("name").lower()
        normalized = LAB_ALIASES[alias]
        value = float(match.group("value"))
        evidence = match.group(0)
        bundle.labs.append(CandidateLab(normalized, value, None, LAB_UNITS.get(normalized), evidence, match.start(), match.end()))
        bundle.facts.append(CandidateFact(
            fact_type="lab",
            concept=normalized,
            value_numeric=value,
            units=LAB_UNITS.get(normalized),
            evidence_text=evidence,
            source_start=match.start(),
            source_end=match.end(),
            observed_datetime=source_datetime,
            source_category=source_category,
        ))

    # Oxygen flow and room-air state.
    for match in OXYGEN_PATTERN.finditer(text):
        flow = float(match.group("flow"))
        evidence = match.group(0)
        bundle.vitals.append(CandidateVital("oxygen_flow", flow, units="L/min", oxygen_device="nasal_cannula", oxygen_flow_lpm=flow, evidence_text=evidence))
        bundle.facts.append(CandidateFact("oxygen_support", "oxygen_flow", value_numeric=flow, units="L/min", evidence_text=evidence, source_start=match.start(), source_end=match.end(), observed_datetime=source_datetime, source_category=source_category))
    for match in ROOM_AIR_PATTERN.finditer(text):
        evidence = match.group(0)
        bundle.vitals.append(CandidateVital("oxygen_support", value_text="room_air", oxygen_device="room_air", evidence_text=evidence))
        bundle.facts.append(CandidateFact("oxygen_support", "oxygen_device", value_text="room_air", evidence_text=evidence, source_start=match.start(), source_end=match.end(), observed_datetime=source_datetime, source_category=source_category))

    # Explicit diagnosis mentions, preserving uncertainty language.
    for phrase, normalized in DIAGNOSIS_PATTERNS:
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", text, flags=re.I):
            prefix = text[max(0, match.start() - 20):match.start()].lower()
            if re.search(r"(?:\bno|\bwithout|\bdenies)\s*$", prefix):
                continue
            certainty = _certainty_for(text, match.start())
            bundle.problems.append(CandidateProblem(match.group(0), normalized, certainty=certainty, status=_status_for(text, match.end()), evidence_text=match.group(0)))

    # Explicit medication actions only. Consultant recommendation text is not evidence of an
    # implemented medication/order state; it is captured separately below as a recommendation.
    if source_category != "consultant_documented":
        for pattern, status in MED_STATUS_PATTERNS:
            for match in pattern.finditer(text):
                display = match.group("med").strip()
                normalized = _normalize_med_name(display)
                if len(normalized) < 2:
                    continue
                bundle.medications.append(CandidateMedication(normalized, display, status=status, evidence_text=match.group(0)))

    for match in CONSULT_PATTERN.finditer(text):
        service = match.group("service").upper() if match.group("service").lower() in {"gi", "id"} else match.group("service").title()
        bundle.consultants.append(CandidateConsult(service, match.group("rec").strip(), match.group(0)))

    for match in PENDING_PATTERN.finditer(text):
        item = re.sub(r"\s+", " ", match.group("item").strip())
        bundle.pending_items.append(CandidatePending("result_or_procedure", item, match.group(0)))


    # Explicit home medication-list semantics. This creates a home-domain state only;
    # it does not imply inpatient administration or discharge intent.
    for match in HOME_MED_PATTERN.finditer(text):
        raw = match.group("meds")
        raw = re.split(r"\b(?:held|continue|continued|stop|stopped|resume|resumed)\b", raw, maxsplit=1, flags=re.I)[0]
        for med in re.split(r"\s*(?:,|\band\b)\s*", raw, flags=re.I):
            med = med.strip(" .;:")
            if not med or len(med) < 2:
                continue
            bundle.medications.append(CandidateMedication(_normalize_med_name(med), med, domain="home", status="active", evidence_text=match.group(0)))

    # Focused physical examination. Only explicit clauses are structured; no normal defaults are invented.
    for match in EXAM_PATTERN.finditer(text):
        for clause in [x.strip() for x in match.group("exam").split(";") if x.strip()]:
            low = clause.lower()
            concept = "exam_finding"
            if any(x in low for x in ("crackle", "wheeze", "rhonchi", "breath sound")):
                concept = "lung_exam"
            elif "edema" in low:
                concept = "edema"
            elif any(x in low for x in ("abdomen", "abdominal")):
                concept = "abdominal_exam"
            elif any(x in low for x in ("orientation", "oriented", "mental status")):
                concept = "mental_status_exam"
            start = match.start("exam") + match.group("exam").find(clause)
            bundle.facts.append(CandidateFact(
                fact_type="exam", concept=concept, value_text=clause, evidence_text=clause,
                source_start=start, source_end=start + len(clause), observed_datetime=source_datetime,
                source_category=source_category,
            ))

    # Disposition / therapy extraction is intentionally literal and source-bound.
    disposition = CandidateDisposition()
    evidence = []
    for pattern, field_name in ((PT_RECOMMEND_PATTERN, "pt_recommendation"), (OT_RECOMMEND_PATTERN, "ot_recommendation"), (SLP_RECOMMEND_PATTERN, "slp_recommendation")):
        match = pattern.search(text)
        if match:
            value = match.group("destination").strip()
            setattr(disposition, field_name, value)
            if field_name == "pt_recommendation":
                disposition.anticipated_destination = value
            evidence.append(match.group(0))
    match = DISCHARGE_PLAN_PATTERN.search(text)
    if match:
        disposition.anticipated_destination = match.group("destination").strip()
        evidence.append(match.group(0))
    match = MOBILITY_PATTERN.search(text)
    if match:
        disposition.mobility_status = f"Ambulates {match.group('distance')} feet with {match.group('detail').strip()}"
        evidence.append(match.group(0))
    match = INPATIENT_NEED_PATTERN.search(text)
    if match:
        barrier_text = match.group("barriers")
        disposition.current_barriers = [x.strip() for x in re.split(r"\s*(?:,|\band\b)\s*", barrier_text, flags=re.I) if x.strip()]
        evidence.append(match.group(0))
    if re.search(r"\bno supplemental oxygen required during therapy session\b", text, re.I):
        disposition.oxygen_need = "No supplemental oxygen required during therapy session"
        evidence.append("No supplemental oxygen required during therapy session")
    elif ROOM_AIR_PATTERN.search(text):
        disposition.oxygen_need = "room air"
    else:
        om = list(OXYGEN_PATTERN.finditer(text))
        if om:
            disposition.oxygen_need = f"{om[-1].group('flow')} L nasal cannula"
    if disposition.anticipated_destination or disposition.current_barriers or disposition.mobility_status or disposition.pt_recommendation or disposition.ot_recommendation or disposition.slp_recommendation:
        disposition.evidence_text = "; ".join(evidence) if evidence else None
        bundle.dispositions.append(disposition)


    # Explicit procedure lifecycle states. Later lifecycle states are reconciled in the service layer.
    for match in PROCEDURE_PATTERN.finditer(text):
        status = match.group("status").lower()
        if status == "canceled":
            status = "cancelled"
        if status == "performed":
            status = "completed"
        bundle.procedures.append(CandidateProcedure(match.group("name").strip(), status, match.group(0)))

    # Final results resolve prior pending items; they do not create new clinical diagnoses.
    for match in FINAL_RESULT_PATTERN.finditer(text):
        item = re.sub(r"\s+", " ", match.group("item").strip())
        result = match.group("result").strip()
        bundle.resolved_items.append(CandidateResolution("result", item, result, match.group(0)))
        bundle.facts.append(CandidateFact(
            fact_type="result_status", concept=item.lower(), value_text=f"final: {result}",
            evidence_text=match.group(0), source_start=match.start(), source_end=match.end(),
            observed_datetime=source_datetime, source_category=source_category,
        ))

    bundle.facts = _dedupe(bundle.facts, lambda x: (x.fact_type, x.concept, x.value_text, x.value_numeric, x.source_start))
    bundle.problems = _dedupe(bundle.problems, lambda x: (x.normalized_name, x.certainty))
    bundle.medications = _dedupe(bundle.medications, lambda x: (x.normalized_name, x.domain, x.status))
    bundle.labs = _dedupe(bundle.labs, lambda x: (x.test_name, x.value_numeric, x.source_start))
    bundle.vitals = _dedupe(bundle.vitals, lambda x: (x.vital_type, x.value_numeric, x.value_text, x.evidence_text))
    bundle.consultants = _dedupe(bundle.consultants, lambda x: (x.service, x.recommendation))
    bundle.pending_items = _dedupe(bundle.pending_items, lambda x: (x.item_type, x.description))
    bundle.dispositions = _dedupe(bundle.dispositions, lambda x: (x.anticipated_destination, tuple(x.current_barriers), x.mobility_status, x.pt_recommendation, x.ot_recommendation, x.slp_recommendation, x.oxygen_need))
    bundle.resolved_items = _dedupe(bundle.resolved_items, lambda x: (x.item_type, x.description.lower(), x.result_text.lower()))
    bundle.procedures = _dedupe(bundle.procedures, lambda x: (x.procedure_name.lower(), x.status))
    return bundle
