# utils_parser.py

import re
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Set, Tuple, Dict


# --------------------------
# Logging configuration
# --------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Default logging setup (only used if the app hasn't configured logging)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# --------------------------
# Constants
# --------------------------
JST = timezone(timedelta(hours=9))  # Japan Standard Time (UTC+9)


# --------------------------
# Main Function
# --------------------------

def parse_threads_data_from_lines(
    lines: List[str],
    processed_ids_set: Set[str],
    verbose: bool = False
) -> Tuple[List[Dict], int]:
    """
    Parses raw text lines copied from a Threads profile page and extracts structured post data.

    Args:
        lines: List of text lines from a Threads profile.
        processed_ids_set: Set of post_ids already processed (updated in place).
        verbose: If True, temporarily sets logging to DEBUG level for this call.

    Returns:
        (parsed_posts_data, newly_added_count)
    """

    # --- Adjust temporary log level if verbose ---
    original_level = logger.level
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled — detailed logs will be shown.")

    parsed_posts_data = []
    newly_added_count = 0

    if not lines:
        logger.warning("Input lines are empty — returning no posts.")
        if verbose:
            logger.setLevel(original_level)
        return [], 0

    logger.info("Starting parsing of %d lines.", len(lines))

    # --- 1. Detect username (account ID) ---
    username = detect_username(lines)
    if not username:
        logger.warning("Could not detect username. Aborting parse.")
        if verbose:
            logger.setLevel(original_level)
        return [], 0
    else:
        logger.info("Detected username: %s", username)

    # --- 2. Find timestamp lines marking posts ---
    timestamp_indices = [
        i for i, line in enumerate(lines)
        if is_timestamp_line(line)
    ]
    logger.debug("Detected %d timestamp markers.", len(timestamp_indices))

    # --- 3. Extract each post block ---
    for idx, ts_i in enumerate(timestamp_indices):
        start = ts_i + 1
        end = timestamp_indices[idx + 1] if idx + 1 < len(timestamp_indices) else len(lines)
        post_block_lines = lines[start:end]

        raw_text = clean_post_text(post_block_lines)
        if not raw_text.strip():
            logger.debug("Skipped post at line %d: empty text after cleaning.", ts_i)
            continue

        time_str = lines[ts_i].strip()
        iso_time = parse_time_string_to_iso(time_str)

        post_id = generate_pseudo_id(username, iso_time, raw_text[:50])

        if post_id in processed_ids_set:
            logger.debug("Skipped duplicate post ID: %s", post_id)
            continue

        post_dict = {
            "username": username,
            "posted_at": iso_time,
            "original_text": raw_text.strip(),
            "post_id": post_id,
            "source_url": "",
            "like_count": 0,
            "retweet_count": 0
        }

        parsed_posts_data.append(post_dict)
        processed_ids_set.add(post_id)
        newly_added_count += 1
        logger.debug("Added new post: %s", post_id)

    logger.info("Parsing complete. %d new posts added.", newly_added_count)

    # --- Restore log level ---
    if verbose:
        logger.setLevel(original_level)
        logger.debug("Verbose mode complete — log level restored.")

    return parsed_posts_data, newly_added_count


# --------------------------
# Helper Functions
# --------------------------

def detect_username(lines: List[str]) -> str:
    """Detects the Threads username (e.g., 'npr' or 'stockstoearn')."""
    for line in lines[:50]:
        line = line.strip()
        if re.fullmatch(r"[A-Za-z0-9._]+", line) and len(line) < 50:
            return line
    return ""


def is_timestamp_line(line: str) -> bool:
    """Checks whether a line looks like a timestamp."""
    line = line.strip()
    if not line:
        return False

    patterns = [
        r"^\d+時間前$",
        r"^\d+日$",
        r"^昨日$",
        r"^\d{4}/\d{1,2}/\d{1,2}$",
    ]
    return any(re.match(p, line) for p in patterns)


def clean_post_text(lines: List[str]) -> str:
    """Cleans a post body, removing noise like link previews, '1 / 2', usernames, etc."""
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip noise
        if re.match(r"^\d+\s*/\s*\d+$", line):  # e.g. "1 / 2"
            continue
        if re.match(r"^https?://", line):
            continue
        if any(domain in line for domain in ["npr.org", "stockstoearn.com"]):
            continue
        if line in ["·", "投稿者"]:
            continue
        if re.match(r"^[A-Za-z0-9._]+$", line):  # user id repeats
            continue
        text_lines.append(line)

    joined = "\n".join(text_lines)
    joined = re.sub(r"`+", "", joined)
    joined = re.sub(r"\s+\n", "\n", joined)
    return joined.strip()


def parse_time_string_to_iso(time_str: str) -> str:
    """Converts relative or absolute time strings to ISO 8601 (UTC)."""
    now_jst = datetime.now(JST)
    time_str = time_str.strip()

    try:
        if re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", time_str):
            dt_jst = datetime.strptime(time_str, "%Y/%m/%d").replace(tzinfo=JST)
        elif re.match(r"^\d+時間前$", time_str):
            hours = int(re.findall(r"\d+", time_str)[0])
            dt_jst = now_jst - timedelta(hours=hours)
        elif re.match(r"^\d+日$", time_str):
            days = int(re.findall(r"\d+", time_str)[0])
            dt_jst = now_jst - timedelta(days=days)
        elif "昨日" in time_str:
            dt_jst = now_jst - timedelta(days=1)
        else:
            dt_jst = now_jst
    except Exception as e:
        logger.warning("Failed to parse time string '%s': %s", time_str, e)
        dt_jst = now_jst

    dt_utc = dt_jst.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pseudo_id(username: str, timestamp: str, text_snippet: str) -> str:
    """Generates a deterministic short hash ID for a post."""
    base = f"{username}|{timestamp}|{text_snippet}".encode("utf-8")
    return hashlib.md5(base).hexdigest()[:10]
