from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd


@dataclass(frozen=True)
class TargetRecord:
    tier: str
    target: str
    gene: str
    aliases: list[str]
    notes: str


def load_targets(path: str | Path = "data/adc_targets.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    df["alias_list"] = df["aliases"].fillna("").apply(
        lambda x: [item.strip() for item in str(x).split(";") if item.strip()]
    )
    return df


def query_terms_for_target(row: pd.Series, include_assets: bool = True) -> list[str]:
    aliases = row.get("alias_list", [])
    core = [row["target"], row["gene"]]
    terms = []
    for term in core + aliases:
        if term and isinstance(term, str) and term not in terms:
            terms.append(term)
    if not include_assets:
        terms = terms[:6]
    return terms
