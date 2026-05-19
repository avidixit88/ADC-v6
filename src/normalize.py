from __future__ import annotations

from typing import Any
import pandas as pd


def _get(d: dict[str, Any], path: list[str], default=None):
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def _join(items, key: str | None = None) -> str:
    if not items:
        return ""
    vals = []
    for item in items:
        val = item.get(key) if key and isinstance(item, dict) else item
        if val and val not in vals:
            vals.append(str(val))
    return "; ".join(vals)


def flatten_study(study: dict[str, Any], matched_target: str, matched_query: str) -> dict[str, Any]:
    protocol = study.get("protocolSection", {})
    idm = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    desc = protocol.get("descriptionModule", {})
    conditions = protocol.get("conditionsModule", {})
    design = protocol.get("designModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    contacts = protocol.get("contactsLocationsModule", {})
    outcomes = protocol.get("outcomesModule", {})

    lead = sponsor.get("leadSponsor", {}) or {}
    collaborators = sponsor.get("collaborators", []) or []
    enrollment = design.get("enrollmentInfo", {}) or {}
    locations = contacts.get("locations", []) or []
    interventions = arms.get("interventions", []) or []

    countries = []
    facilities = []
    for loc in locations:
        country = loc.get("country")
        facility = loc.get("facility")
        city = loc.get("city")
        state = loc.get("state")
        if country and country not in countries:
            countries.append(country)
        label = ", ".join([x for x in [facility, city, state, country] if x])
        if label and label not in facilities:
            facilities.append(label)

    primary_outcomes = outcomes.get("primaryOutcomes", []) or []
    secondary_outcomes = outcomes.get("secondaryOutcomes", []) or []

    return {
        "target": matched_target,
        "matched_query": matched_query,
        "nct_id": idm.get("nctId", ""),
        "brief_title": idm.get("briefTitle", ""),
        "official_title": idm.get("officialTitle", ""),
        "overall_status": status.get("overallStatus", ""),
        "start_date": _get(status, ["startDateStruct", "date"], ""),
        "start_date_type": _get(status, ["startDateStruct", "type"], ""),
        "primary_completion_date": _get(status, ["primaryCompletionDateStruct", "date"], ""),
        "completion_date": _get(status, ["completionDateStruct", "date"], ""),
        "last_update_posted": _get(status, ["lastUpdatePostDateStruct", "date"], ""),
        "lead_sponsor": lead.get("name", ""),
        "lead_sponsor_class": lead.get("class", ""),
        "collaborators": _join(collaborators, "name"),
        "conditions": _join(conditions.get("conditions", [])),
        "phases": _join(design.get("phases", [])),
        "study_type": design.get("studyType", ""),
        "allocation": design.get("designInfo", {}).get("allocation", ""),
        "primary_purpose": design.get("designInfo", {}).get("primaryPurpose", ""),
        "enrollment_count": enrollment.get("count"),
        "enrollment_type": enrollment.get("type", ""),
        "interventions": _join(interventions, "name"),
        "intervention_types": _join(interventions, "type"),
        "countries": "; ".join(countries),
        "site_count": len(locations),
        "sample_facilities": "; ".join(facilities[:6]),
        "primary_outcomes": _join(primary_outcomes, "measure"),
        "secondary_outcomes": _join(secondary_outcomes, "measure"),
        "brief_summary": desc.get("briefSummary", ""),
    }


def normalize_studies(studies: list[dict[str, Any]], target: str, query: str) -> pd.DataFrame:
    rows = [flatten_study(study, target, query) for study in studies]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["nct_id"])
    df["enrollment_count"] = pd.to_numeric(df["enrollment_count"], errors="coerce").fillna(0).astype(int)
    df["start_year"] = pd.to_datetime(df["start_date"], errors="coerce").dt.year
    df["last_update_year"] = pd.to_datetime(df["last_update_posted"], errors="coerce").dt.year
    return df
