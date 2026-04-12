"""Shared numeric and version constants for reports and cache."""

# JSON report snapshot schema; bump when required metadata shape changes.
REPORT_JSON_SCHEMA_VERSION: int = 1

# PDF vertical spacing scale (points).
PDF_SPACE_SMALL_PT: int = 4
PDF_SPACE_MEDIUM_PT: int = 8
PDF_SPACE_LARGE_PT: int = 12

# World map beside ranked table: map column as a share of content width (rest is table).
PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE: float = 2.0 / 3.0

# Max rows in the narrow table beside the map (labels truncate in narrow cells).
PDF_MAP_SIDE_TABLE_MAX_ROWS: int = 10

# Ranked tables (label, count, bar): cap third column width as a share of inner width.
PDF_RANKED_BAR_COLUMN_MAX_SHARE: float = 0.18

# Height of the horizontal bar track inside each row (points).
PDF_RANKED_BAR_TRACK_HEIGHT_PT: float = 4.0

# Top and bottom padding per body row in ranked tables (points).
PDF_RANKED_TABLE_ROW_PAD_PT: int = 2

# Executive action: if Always Use HTTPS is on but encrypted traffic share is below (100 - this)
# percent of requests, emit the HTTPS gap review action (percentage points of unencrypted share).
HTTPS_ENCRYPTED_GAP_ACTION_MAX_PCT: float = 5.0

# Executive verdict: pipeline warning strings must exceed this count to set ``warnings_present``.
# Single cache misses do not downgrade the verdict below healthy (when zone is active).
VERDICT_WARN_THRESHOLD: int = 3

# Security posture score: summed ``SECT_RISKS`` weights at this level yield score 0 (linear scale).
SECURITY_POSTURE_REFERENCE_RISK_WEIGHT: float = 60.0
