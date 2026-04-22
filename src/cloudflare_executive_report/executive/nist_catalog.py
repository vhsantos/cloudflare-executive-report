"""NIST SP 800-53 control titles and CPRT catalog URLs for the PDF appendix."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class NistSourceLine(Protocol):
    """Minimal shape for lines that carry check ids and NIST tags."""

    check_id: str
    nist: tuple[str, ...]


NIST_CONTROL_TITLES: dict[str, str] = {
    "SC-7": "Boundary Protection",
    "SC-8": "Transmission Confidentiality and Integrity",
    "SC-12": "Cryptographic Key Establishment and Management",
    "SC-13": "Cryptographic Protection",
    "SC-18": "Mobile Code",
    "SC-20": "Secure Name / Address Resolution Service",
    "SI-3": "Malicious Code Protection",
    "SI-4": "Information System Monitoring",
    "SI-7": "Software, Firmware, and Information Integrity",
    "AU-2": "Audit Events",
    "AU-11": "Audit Record Retention",
    "CM-6": "Configuration Settings",
}

NIST_CONTROL_URLS: dict[str, str] = {
    "SC-7": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SC-7",
    "SC-8": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SC-8",
    "SC-12": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SC-12",
    "SC-13": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SC-13",
    "SC-18": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SC-18",
    "SC-20": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SC-20",
    "SI-3": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SI-3",
    "SI-4": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SI-4",
    "SI-7": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/SI-7",
    "AU-2": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/AU-2",
    "AU-11": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/AU-11",
    "CM-6": "https://csrc.nist.gov/projects/cprt/catalog#/cprt/CM-6",
}


def build_nist_reference_rows(lines: Sequence[NistSourceLine]) -> list[dict[str, object]]:
    """Build sorted appendix rows: one entry per NIST id with linked check ids."""
    by_nist: dict[str, dict[str, object]] = {}
    for line in lines:
        for nid in line.nist:
            if nid not in by_nist:
                by_nist[nid] = {
                    "nist_id": nid,
                    "title": NIST_CONTROL_TITLES.get(nid, ""),
                    "url": NIST_CONTROL_URLS.get(nid, ""),
                    "check_ids": [],
                }
            row = by_nist[nid]
            ids = row["check_ids"]
            if not isinstance(ids, list):
                raise TypeError(f"Expected list for NIST check_ids, got {type(ids)}")
            cid = line.check_id
            if cid not in ids:
                ids.append(cid)
    for row in by_nist.values():
        ids = row["check_ids"]
        if not isinstance(ids, list):
            raise TypeError(f"Expected list for NIST check_ids, got {type(ids)}")
        ids.sort()
    return sorted(by_nist.values(), key=lambda r: str(r["nist_id"]))
