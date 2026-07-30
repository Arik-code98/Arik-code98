from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
import urllib.request
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "generated"
LOGIN = os.environ.get("GH_LOGIN", "Arik-code98")

CARD_BG = "#130f0c"
CARD_EDGE = "#2d221c"
PANEL = "#1b1511"
TEXT = "#f4e6d6"
MUTED = "#b39b84"
ACCENT = "#d49a66"
ACCENT_ALT = "#8d5a34"
HEAT = ["#3a2b22", "#64412a", "#8d5a34", "#c27d47", "#f0b36f"]
YEAR_RAMP = " .:-=+*#%@"


@dataclass
class ContributionDay:
    day: date
    count: int


def github_request(url: str) -> urllib.request.Request:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{LOGIN}-profile-generator",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def get_json(url: str) -> object:
    with urllib.request.urlopen(github_request(url)) as response:
        return json.load(response)


def get_text(url: str) -> str:
    with urllib.request.urlopen(github_request(url)) as response:
        return response.read().decode("utf-8")


def fetch_profile() -> dict:
    return get_json(f"https://api.github.com/users/{LOGIN}")


def fetch_repositories() -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/users/{LOGIN}/repos"
            f"?per_page=100&page={page}&sort=updated&type=owner"
        )
        batch = get_json(url)
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(repo for repo in batch if isinstance(repo, dict) and not repo.get("fork"))
        page += 1
    return repos


def fetch_languages(repositories: list[dict]) -> tuple[Counter, Counter]:
    language_bytes: Counter[str] = Counter()
    repo_counts: Counter[str] = Counter()
    for repo in repositories:
        primary = repo.get("language")
        if primary:
            repo_counts[primary] += 1
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        data = get_json(languages_url)
        if isinstance(data, dict):
            for language, size in data.items():
                if isinstance(size, int):
                    language_bytes[language] += size
    return language_bytes, repo_counts


def contribution_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=364), today


def fetch_contributions() -> list[ContributionDay]:
    start, end = contribution_window()
    params = urllib.parse.urlencode({"from": start.isoformat(), "to": end.isoformat()})
    html = get_text(f"https://github.com/users/{LOGIN}/contributions?{params}")

    pattern = re.compile(
        r'data-date="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*class="ContributionCalendar-day"></td>\s*'
        r'<tool-tip[^>]*>(?P<tooltip>.*?)</tool-tip>',
        re.S,
    )
    days: list[ContributionDay] = []
    for match in pattern.finditer(html):
        tooltip = unescape(match.group("tooltip"))
        count_match = re.search(r"(\d[\d,]*) contribution", tooltip)
        count = int(count_match.group(1).replace(",", "")) if count_match else 0
        days.append(ContributionDay(day=date.fromisoformat(match.group("date")), count=count))

    if len(days) < 300:
        raise RuntimeError("Could not parse enough contribution days from GitHub.")

    return sorted(days, key=lambda item: item.day)


def compute_streaks(days: list[ContributionDay]) -> dict:
    longest_len = 0
    longest_start: date | None = None
    longest_end: date | None = None
    current_len = 0
    current_start: date | None = None
    active_weeks = 0

    week_totals: OrderedDict[date, int] = OrderedDict()
    run_len = 0
    run_start: date | None = None
    previous_day: date | None = None

    for item in days:
        week_start = item.day - timedelta(days=(item.day.weekday() + 1) % 7)
        week_totals.setdefault(week_start, 0)
        week_totals[week_start] += item.count

        if item.count > 0:
            if run_start is None or previous_day is None or item.day != previous_day + timedelta(days=1):
                run_start = item.day
                run_len = 1
            else:
                run_len += 1

            if run_len > longest_len:
                longest_len = run_len
                longest_start = run_start
                longest_end = item.day
        else:
            run_start = None
            run_len = 0

        previous_day = item.day

    for total in week_totals.values():
        if total > 0:
            active_weeks += 1

    for item in reversed(days):
        if item.count > 0:
            current_len += 1
            current_start = item.day
        else:
            break

    return {
        "longest_len": longest_len,
        "longest_start": longest_start,
        "longest_end": longest_end,
        "current_len": current_len,
        "current_start": current_start,
        "current_end": days[-1].day if current_len else None,
        "active_weeks": active_weeks,
        "week_totals": list(week_totals.items()),
    }


def fmt_day(value: date | None) -> str:
    if value is None:
        return "n/a"
    return value.strftime("%b %d, %Y")


def total_stars(repositories: list[dict]) -> int:
    return sum(int(repo.get("stargazers_count", 0)) for repo in repositories)


def build_svg(width: int, height: int, body: str, title: str, description: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(description)}</desc>
  <rect width="{width}" height="{height}" rx="22" fill="{CARD_BG}" />
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="21" fill="none" stroke="{CARD_EDGE}" />
  {body}
</svg>
"""


def metric_block(x: int, y: int, label: str, value: str) -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{MUTED}" font-size="12">{escape(label)}</text>'
        f'<text x="{x}" y="{y + 26}" fill="{TEXT}" font-size="22" font-weight="700">{escape(value)}</text>'
    )


def generate_stats_svg(profile: dict, repositories: list[dict], streaks: dict, contributions: list[ContributionDay]) -> None:
    total = sum(item.count for item in contributions)
    created = datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00")).date()
    age_days = (date.today() - created).days
    weekly_totals = [total for _, total in streaks["week_totals"]]
    chart_x = 456
    chart_y = 152
    chart_w = 360
    chart_h = 70

    points: list[str] = []
    max_weekly = max(weekly_totals) if weekly_totals else 1
    for index, value in enumerate(weekly_totals):
        x = chart_x + (index / max(1, len(weekly_totals) - 1)) * chart_w
        y = chart_y - (value / max_weekly) * chart_h
        points.append(f"{x:.2f},{y:.2f}")

    sparkline = ""
    if points:
        sparkline = (
            f'<polyline fill="none" stroke="{ACCENT}" stroke-width="3" '
            f'stroke-linecap="round" stroke-linejoin="round" points="{" ".join(points)}" />'
        )

    body = f"""
  <text x="36" y="38" fill="{MUTED}" font-size="12" letter-spacing="1.1">GITHUB OUTPUT / LAST 365 DAYS</text>
  <text x="36" y="102" fill="{TEXT}" font-size="62" font-weight="700">{total}</text>
  <text x="36" y="132" fill="{MUTED}" font-size="18">public contributions generated from your own repository</text>
  {metric_block(36, 178, "public repos", str(profile.get("public_repos", 0)))}
  {metric_block(196, 178, "stars earned", str(total_stars(repositories)))}
  {metric_block(336, 178, "followers", str(profile.get("followers", 0)))}
  <rect x="430" y="54" width="392" height="146" rx="16" fill="{PANEL}" stroke="{CARD_EDGE}" />
  <text x="456" y="82" fill="{TEXT}" font-size="16" font-weight="700">weekly rhythm</text>
  <text x="456" y="104" fill="{MUTED}" font-size="13">one year of output, grouped into Sunday-based weeks</text>
  <line x1="{chart_x}" y1="{chart_y}" x2="{chart_x + chart_w}" y2="{chart_y}" stroke="{CARD_EDGE}" />
  {sparkline}
  {metric_block(456, 178, "following", str(profile.get("following", 0)))}
  {metric_block(596, 178, "account age", f"{age_days} days")}
  {metric_block(716, 178, "active weeks", str(streaks["active_weeks"]))}
"""
    svg = build_svg(
        860,
        250,
        body,
        "GitHub output card for Arik Chakraborty",
        "A self-hosted card showing total contributions, weekly rhythm, and public GitHub account metrics.",
    )
    (OUTPUT_DIR / "stats.svg").write_text(svg, encoding="utf-8")


def generate_streak_svg(streaks: dict, contributions: list[ContributionDay]) -> None:
    last_active = next((item.day for item in reversed(contributions) if item.count > 0), None)
    current_text = str(streaks["current_len"]) if streaks["current_len"] else "0"
    current_range = (
        f"{fmt_day(streaks['current_start'])} -> {fmt_day(streaks['current_end'])}"
        if streaks["current_len"]
        else f"last active {fmt_day(last_active)}"
    )
    longest_range = f"{fmt_day(streaks['longest_start'])} -> {fmt_day(streaks['longest_end'])}"

    body = f"""
  <text x="36" y="38" fill="{MUTED}" font-size="12" letter-spacing="1.1">STREAK / CONSISTENCY</text>
  <rect x="36" y="56" width="250" height="116" rx="16" fill="{PANEL}" stroke="{CARD_EDGE}" />
  <text x="58" y="86" fill="{MUTED}" font-size="13">current streak</text>
  <text x="58" y="132" fill="{TEXT}" font-size="48" font-weight="700">{current_text}</text>
  <text x="58" y="156" fill="{MUTED}" font-size="13">{escape(current_range)}</text>

  <rect x="304" y="56" width="250" height="116" rx="16" fill="{PANEL}" stroke="{CARD_EDGE}" />
  <text x="326" y="86" fill="{MUTED}" font-size="13">longest streak</text>
  <text x="326" y="132" fill="{TEXT}" font-size="48" font-weight="700">{streaks["longest_len"]}</text>
  <text x="326" y="156" fill="{MUTED}" font-size="13">{escape(longest_range)}</text>

  <rect x="572" y="56" width="252" height="116" rx="16" fill="{PANEL}" stroke="{CARD_EDGE}" />
  <text x="594" y="86" fill="{MUTED}" font-size="13">active weeks this year</text>
  <text x="594" y="132" fill="{TEXT}" font-size="48" font-weight="700">{streaks["active_weeks"]}</text>
  <text x="594" y="156" fill="{MUTED}" font-size="13">weeks with at least one public contribution</text>
"""
    svg = build_svg(
        860,
        190,
        body,
        "GitHub streak card for Arik Chakraborty",
        "A self-hosted card showing the current streak, longest streak, and active weeks.",
    )
    (OUTPUT_DIR / "streak.svg").write_text(svg, encoding="utf-8")


def generate_languages_svg(language_bytes: Counter, repo_counts: Counter) -> None:
    top_bytes = language_bytes.most_common(5)
    max_value = top_bytes[0][1] if top_bytes else 1

    bars: list[str] = []
    for index, (language, value) in enumerate(top_bytes):
        y = 78 + index * 30
        width = 320 * (value / max_value)
        percentage = (value / max(1, sum(language_bytes.values()))) * 100
        bars.append(
            f'<text x="46" y="{y - 6}" fill="{TEXT}" font-size="14">{escape(language)}</text>'
            f'<rect x="46" y="{y}" width="320" height="10" rx="5" fill="{ACCENT_ALT}" opacity="0.32" />'
            f'<rect x="46" y="{y}" width="{width:.2f}" height="10" rx="5" fill="{ACCENT}" />'
            f'<text x="380" y="{y + 9}" fill="{MUTED}" font-size="12">{percentage:.1f}%</text>'
        )

    chips: list[str] = []
    chip_x = 470
    chip_y = 82
    for index, (language, count) in enumerate(repo_counts.most_common(8)):
        x = chip_x + (index % 2) * 164
        y = chip_y + (index // 2) * 38
        chips.append(
            f'<rect x="{x}" y="{y}" width="144" height="28" rx="14" fill="{PANEL}" stroke="{CARD_EDGE}" />'
            f'<text x="{x + 14}" y="{y + 19}" fill="{TEXT}" font-size="13">{escape(language)}</text>'
            f'<text x="{x + 118}" y="{y + 19}" fill="{ACCENT}" font-size="13" text-anchor="end">{count}</text>'
        )

    body = f"""
  <text x="36" y="38" fill="{MUTED}" font-size="12" letter-spacing="1.1">LANGUAGES / PUBLIC REPOSITORIES</text>
  <text x="46" y="64" fill="{TEXT}" font-size="16" font-weight="700">by bytes pushed</text>
  {''.join(bars)}
  <text x="470" y="64" fill="{TEXT}" font-size="16" font-weight="700">by repo count</text>
  {''.join(chips)}
"""
    svg = build_svg(
        860,
        260,
        body,
        "Language usage card for Arik Chakraborty",
        "A self-hosted card showing public language usage by bytes and repository count.",
    )
    (OUTPUT_DIR / "langs.svg").write_text(svg, encoding="utf-8")


def generate_year_svg(contributions: list[ContributionDay]) -> None:
    counts = [item.count for item in contributions]
    max_count = max(counts) if counts else 1
    weeks: OrderedDict[date, list[str]] = OrderedDict()
    for item in contributions:
        week_start = item.day - timedelta(days=(item.day.weekday() + 1) % 7)
        weeks.setdefault(week_start, [" "] * 7)
        day_index = (item.day.weekday() + 1) % 7
        glyph_index = 0 if item.count == 0 else max(1, round((item.count / max_count) * (len(YEAR_RAMP) - 1)))
        weeks[week_start][day_index] = YEAR_RAMP[glyph_index]

    columns = list(weeks.values())
    cell_w = 14
    cell_h = 15
    start_x = 110
    start_y = 74
    month_labels = OrderedDict()
    for week_start in weeks.keys():
        month_labels.setdefault(week_start.strftime("%b"), len(month_labels))

    glyphs: list[str] = []
    for col_index, column in enumerate(columns):
        for row_index, glyph in enumerate(column):
            x = start_x + col_index * cell_w
            y = start_y + row_index * cell_h
            glyphs.append(
                f'<text x="{x}" y="{y}" fill="{TEXT if glyph != " " else ACCENT_ALT}" font-size="12" '
                f'font-family="Consolas,\'Liberation Mono\',Menlo,monospace">{escape(glyph)}</text>'
            )

    labels: list[str] = []
    first_seen: set[str] = set()
    for col_index, week_start in enumerate(weeks.keys()):
        label = week_start.strftime("%b")
        if label in first_seen:
            continue
        first_seen.add(label)
        labels.append(f'<text x="{start_x + col_index * cell_w}" y="48" fill="{MUTED}" font-size="11">{label}</text>')

    weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    weekday_labels = [
        f'<text x="46" y="{start_y + index * cell_h}" fill="{MUTED}" font-size="11">{label}</text>'
        for index, label in enumerate(weekdays)
    ]

    body = f"""
  <text x="36" y="32" fill="{MUTED}" font-size="12" letter-spacing="1.1">YEAR / ONE GLYPH PER DAY</text>
  <text x="36" y="50" fill="{TEXT}" font-size="15" font-weight="700">a contribution heatmap drawn with the same ASCII logic as the portrait</text>
  {''.join(labels)}
  {''.join(weekday_labels)}
  {''.join(glyphs)}
"""
    svg = build_svg(
        900,
        190,
        body,
        "Year-at-a-glance card for Arik Chakraborty",
        "A self-hosted contribution heatmap using ASCII-style glyph intensity.",
    )
    (OUTPUT_DIR / "year.svg").write_text(svg, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile = fetch_profile()
    repositories = fetch_repositories()
    contributions = fetch_contributions()
    streaks = compute_streaks(contributions)
    language_bytes, repo_counts = fetch_languages(repositories)

    generate_stats_svg(profile, repositories, streaks, contributions)
    generate_streak_svg(streaks, contributions)
    generate_languages_svg(language_bytes, repo_counts)
    generate_year_svg(contributions)
    print(f"Wrote generated stats for {LOGIN}")


if __name__ == "__main__":
    main()

