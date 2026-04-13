"""Project-wide constants.

Keep this module for shared values used across multiple domains (PDF, executive, report schema).
Use clear prefixes to keep ownership obvious.
"""

# ============================================================================
# EMAIL / SMTP
# ============================================================================

# Socket timeout (seconds) for SMTP and SMTP_SSL connections.
SMTP_TIMEOUT_SECONDS: int = 30


# ============================================================================
# SCHEMA
# ============================================================================

# JSON report snapshot schema; bump when metadata shape changes.
REPORT_JSON_SCHEMA_VERSION: int = 1


# ============================================================================
# PDF LAYOUT (points unless noted)
# ============================================================================

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


# ============================================================================
# EXECUTIVE / VERDICT
# ============================================================================

# Executive action: if Always Use HTTPS is on but encrypted traffic share is below (100 - this)
# percent of requests, emit the HTTPS gap review action (percentage points of unencrypted share).
HTTPS_ENCRYPTED_GAP_ACTION_MAX_PCT: float = 5.0

# Executive verdict: pipeline warning strings must exceed this count to set ``warnings_present``.
VERDICT_WARN_THRESHOLD: int = 3

# Security posture score: summed ``SECT_RISKS`` weights at this level yield score 0 (linear scale).
SECURITY_POSTURE_REFERENCE_RISK_WEIGHT: float = 60.0

# HSTS recommended minimum max-age (1 year) for zone setting ``security_header``.
HSTS_RECOMMENDED_MAX_AGE_SECONDS: int = 31536000


# ============================================================================
# EXECUTIVE / RELIABILITY (HTTP adaptive, 0-100 percentages)
# ============================================================================

RELIABILITY_5XX_HEALTHY_MAX: float = 0.5
RELIABILITY_5XX_WARNING_MAX: float = 5.0
