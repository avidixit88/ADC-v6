from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import requests

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


@dataclass
class ClinicalTrialsClient:
    timeout: int = 30
    page_size: int = 100
    pause_seconds: float = 0.15

    def search(self, query: str, max_records: int = 300) -> list[dict[str, Any]]:
        studies: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(studies) < max_records:
            params = {
                "query.term": query,
                "pageSize": min(self.page_size, max_records - len(studies)),
                "format": "json",
            }
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(BASE_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            studies.extend(payload.get("studies", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            time.sleep(self.pause_seconds)
        return studies

    @staticmethod
    def clinicaltrials_url(query: str) -> str:
        return f"https://clinicaltrials.gov/search?term={quote_plus(query)}"
