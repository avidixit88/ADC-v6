from __future__ import annotations

from datetime import datetime
import re
import pandas as pd

ACTIVE_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"}
LATE_PHASES = {"PHASE2", "PHASE3", "PHASE2_PHASE3"}
PHASE_ORDER = ["EARLY_PHASE1", "PHASE1", "PHASE1_PHASE2", "PHASE2", "PHASE2_PHASE3", "PHASE3", "PHASE4", "NOT_APPLICABLE", "UNKNOWN"]
PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE1_PHASE2": "Phase 1/2",
    "PHASE2": "Phase 2",
    "PHASE2_PHASE3": "Phase 2/3",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NOT_APPLICABLE": "Not applicable",
    "UNKNOWN": "Unspecified phase",
    "": "Unspecified phase",
}


def normalize_phase(raw) -> str:
    """Turn ClinicalTrials.gov phase strings/lists into one canonical bucket."""
    if raw is None or pd.isna(raw):
        return "UNKNOWN"
    s = str(raw).strip().upper()
    if not s or s in {"N/A", "NA", "NONE", "NULL", "UNKNOWN"}:
        return "UNKNOWN"
    tokens = [t.strip() for t in re.split(r"[;,|/]+", s) if t.strip()]
    joined = " ".join(tokens)
    has_early = "EARLY_PHASE1" in joined or "EARLY PHASE 1" in joined
    has_p1 = has_early or "PHASE1" in joined or "PHASE 1" in joined
    has_p2 = "PHASE2" in joined or "PHASE 2" in joined
    has_p3 = "PHASE3" in joined or "PHASE 3" in joined
    has_p4 = "PHASE4" in joined or "PHASE 4" in joined
    if "NOT_APPLICABLE" in joined or "NOT APPLICABLE" in joined:
        return "NOT_APPLICABLE"
    if has_p2 and has_p3:
        return "PHASE2_PHASE3"
    if has_p1 and has_p2:
        return "PHASE1_PHASE2"
    if has_early:
        return "EARLY_PHASE1"
    if has_p4:
        return "PHASE4"
    if has_p3:
        return "PHASE3"
    if has_p2:
        return "PHASE2"
    if has_p1:
        return "PHASE1"
    cleaned = s.replace("; ", "_").replace(" ", "_").replace("-", "_")
    return cleaned if cleaned in PHASE_LABELS else "UNKNOWN"


def add_activity_flags(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if d.empty:
        return d
    d["overall_status"] = d.get("overall_status", pd.Series(dtype=str)).fillna("").astype(str)
    d["phase_bucket"] = d.get("phases", pd.Series(dtype=str)).apply(normalize_phase)
    d["phase_label"] = d["phase_bucket"].map(PHASE_LABELS).fillna(d["phase_bucket"].str.replace("_", " ").str.title())
    d["is_active"] = d["overall_status"].isin(ACTIVE_STATUSES)
    d["is_recruiting"] = d["overall_status"].eq("RECRUITING")
    d["has_late_phase"] = d["phase_bucket"].apply(lambda x: any(p == str(x) or p in str(x) for p in LATE_PHASES))
    d["enrollment_count"] = pd.to_numeric(d.get("enrollment_count", 0), errors="coerce").fillna(0).astype(int)
    if "start_year" not in d.columns:
        d["start_year"] = pd.to_datetime(d.get("start_date", pd.Series(dtype=str)), errors="coerce").dt.year
    return d


def target_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = add_activity_flags(df)
    grouped = d.groupby("target", dropna=False).agg(
        total_trials=("nct_id", "nunique"),
        active_trials=("is_active", "sum"),
        recruiting_trials=("is_recruiting", "sum"),
        cumulative_enrollment=("enrollment_count", "sum"),
        active_enrollment=("enrollment_count", lambda s: int(s[d.loc[s.index, "is_active"]].sum())),
        avg_enrollment=("enrollment_count", "mean"),
        sponsor_count=("lead_sponsor", "nunique"),
        country_count=("countries", lambda s: len(set("; ".join(s.dropna()).split("; "))) if len(s.dropna()) else 0),
        late_phase_trials=("has_late_phase", "sum"),
        latest_update=("last_update_posted", "max"),
        earliest_start=("start_date", "min"),
    ).reset_index()
    grouped["heat_score"] = (
        grouped["active_trials"] * 3
        + grouped["recruiting_trials"] * 4
        + grouped["late_phase_trials"] * 5
        + grouped["sponsor_count"] * 1.5
        + grouped["country_count"] * 0.5
        + (grouped["active_enrollment"] / 100).clip(upper=30)
    ).round(1)
    return grouped.sort_values("heat_score", ascending=False)


def phase_distribution(df: pd.DataFrame, active_only: bool = False, include_unspecified: bool = False) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["phase_bucket", "phase_label", "count", "enrollment"])
    d = add_activity_flags(df)
    if active_only:
        d = d[d["is_active"]]
    if not include_unspecified:
        d = d[~d["phase_bucket"].isin(["UNKNOWN", "NOT_APPLICABLE"])]
    grouped = d.groupby(["phase_bucket", "phase_label"], dropna=False).agg(
        count=("nct_id", "nunique"),
        enrollment=("enrollment_count", "sum"),
    ).reset_index()
    grouped["phase_sort"] = grouped["phase_bucket"].apply(lambda x: PHASE_ORDER.index(x) if x in PHASE_ORDER else 99)
    grouped = grouped.sort_values("phase_sort")
    return grouped[["phase_bucket", "phase_label", "count", "enrollment"]]


def status_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["overall_status", "count"])
    d = add_activity_flags(df)
    return d.groupby("overall_status").size().reset_index(name="count").sort_values("count", ascending=False)


def yearly_trial_momentum(df: pd.DataFrame, current_year: int | None = None, include_future: bool = False) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["start_year", "new_trials", "active_trials", "enrollment"])
    current_year = current_year or datetime.now().year
    d = add_activity_flags(df)
    d = d.dropna(subset=["start_year"]).copy()
    if d.empty:
        return pd.DataFrame(columns=["start_year", "new_trials", "active_trials", "enrollment"])
    d["start_year"] = d["start_year"].astype(int)
    if not include_future:
        d = d[d["start_year"] <= current_year]
    grouped = d.groupby("start_year").agg(
        new_trials=("nct_id", "nunique"),
        active_trials=("is_active", "sum"),
        enrollment=("enrollment_count", "sum"),
    ).reset_index().sort_values("start_year")
    grouped["yoy_delta"] = grouped["new_trials"].diff().fillna(0).astype(int)
    grouped["yoy_pct"] = grouped["new_trials"].pct_change().replace([float("inf"), -float("inf")], pd.NA)
    return grouped


def yoy_summary(df: pd.DataFrame, current_year: int | None = None) -> dict[str, int | float | str | None]:
    current_year = current_year or datetime.now().year
    momentum = yearly_trial_momentum(df, current_year=current_year, include_future=False)
    if momentum.empty:
        return {"this_year": 0, "last_year": 0, "delta": 0, "pct": None, "label": "No dated starts", "current_year": current_year, "last_year_label": current_year - 1}
    this_year = int(momentum.loc[momentum["start_year"].eq(current_year), "new_trials"].sum())
    last_year = int(momentum.loc[momentum["start_year"].eq(current_year - 1), "new_trials"].sum())
    delta = this_year - last_year
    pct = None if last_year == 0 else delta / last_year
    return {"this_year": this_year, "last_year": last_year, "delta": delta, "pct": pct, "label": f"{current_year} YTD vs {current_year - 1}", "current_year": current_year, "last_year_label": current_year - 1}


def target_year_heatmap(df: pd.DataFrame, current_year: int | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    current_year = current_year or datetime.now().year
    d = add_activity_flags(df).dropna(subset=["start_year"]).copy()
    if d.empty:
        return pd.DataFrame()
    d["start_year"] = d["start_year"].astype(int)
    d = d[d["start_year"] <= current_year]
    return d.pivot_table(index="target", columns="start_year", values="nct_id", aggfunc="nunique", fill_value=0)


def target_phase_heatmap(df: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = add_activity_flags(df)
    if active_only:
        d = d[d["is_active"]]
    d = d[~d["phase_bucket"].isin(["UNKNOWN", "NOT_APPLICABLE"])]
    if d.empty:
        return pd.DataFrame()
    table = d.pivot_table(index="target", columns="phase_label", values="nct_id", aggfunc="nunique", fill_value=0)
    phase_cols = [PHASE_LABELS[p] for p in PHASE_ORDER if PHASE_LABELS[p] in table.columns]
    remaining = [c for c in table.columns if c not in phase_cols]
    return table[phase_cols + remaining]


def sponsor_activity(df: pd.DataFrame, active_only: bool = True, limit: int = 12, by_target: bool = False) -> pd.DataFrame:
    if df.empty:
        cols = ["target", "lead_sponsor", "trials", "active_trials", "enrollment"] if by_target else ["lead_sponsor", "trials", "active_trials", "enrollment", "targets"]
        return pd.DataFrame(columns=cols)
    d = add_activity_flags(df)
    if active_only:
        d = d[d["is_active"]]
    if d.empty:
        cols = ["target", "lead_sponsor", "trials", "active_trials", "enrollment"] if by_target else ["lead_sponsor", "trials", "active_trials", "enrollment", "targets"]
        return pd.DataFrame(columns=cols)
    if by_target:
        grouped = d.groupby(["target", "lead_sponsor"], dropna=False).agg(
            trials=("nct_id", "nunique"),
            active_trials=("is_active", "sum"),
            enrollment=("enrollment_count", "sum"),
        ).reset_index()
        return grouped.sort_values(["target", "active_trials", "enrollment"], ascending=[True, False, False]).groupby("target").head(limit).reset_index(drop=True)
    grouped = d.groupby("lead_sponsor", dropna=False).agg(
        trials=("nct_id", "nunique"),
        active_trials=("is_active", "sum"),
        enrollment=("enrollment_count", "sum"),
        targets=("target", lambda s: "; ".join(sorted(set(s.dropna())))[:140]),
    ).reset_index()
    return grouped.sort_values(["active_trials", "enrollment", "trials"], ascending=False).head(limit)


def target_momentum_table(df: pd.DataFrame, current_year: int | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["target", "new_trials_current_ytd", "new_trials_prior_year", "yoy_delta", "active_trials", "active_enrollment", "phase2plus_active"])
    current_year = current_year or datetime.now().year
    d = add_activity_flags(df)
    d = d.dropna(subset=["start_year"]).copy()
    d["start_year"] = d["start_year"].astype("Int64")
    d = d[d["start_year"] <= current_year]
    rows = []
    for target, tdf in d.groupby("target"):
        cur = int(tdf.loc[tdf["start_year"].eq(current_year), "nct_id"].nunique())
        prev = int(tdf.loc[tdf["start_year"].eq(current_year - 1), "nct_id"].nunique())
        active = tdf[tdf["is_active"]]
        phase2plus = int(active[active["phase_bucket"].isin(["PHASE2", "PHASE2_PHASE3", "PHASE3"])] ["nct_id"].nunique())
        rows.append({
            "target": target,
            "new_trials_current_ytd": cur,
            "new_trials_prior_year": prev,
            "yoy_delta": cur - prev,
            "active_trials": int(active["nct_id"].nunique()),
            "active_enrollment": int(active["enrollment_count"].sum()),
            "phase2plus_active": phase2plus,
        })
    return pd.DataFrame(rows).sort_values(["yoy_delta", "active_enrollment"], ascending=False)
