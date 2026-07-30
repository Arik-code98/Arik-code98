from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape, unescape
from pathlib import Path

from generate_portrait import build_ascii_rows, render_ascii_layers

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "generated"
LOGIN = os.environ.get("GH_LOGIN", "Arik-code98")

BG = "#0d1117"
EDGE = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
LINK = "#58a6ff"
MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
YEAR_RAMP = " .:+#@"

FALLBACK_PROFILE = {
    "login": "Arik-code98",
    "name": "Arik Chakraborty",
    "public_repos": 21,
    "followers": 4,
    "following": 6,
    "created_at": "2025-07-04T08:53:35Z",
}

FALLBACK_REPOS = [
    {"name": "Portfolio", "description": "Personal portfolio website", "language": "TypeScript", "stargazers_count": 0, "updated_at": "2026-07-25T13:03:17Z", "size": 320},
    {"name": "ai-product-intelligence-system", "description": None, "language": "Jupyter Notebook", "stargazers_count": 0, "updated_at": "2026-06-27T12:40:44Z", "size": 260},
    {"name": "langgraph-agent", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-25T15:06:06Z", "size": 120},
    {"name": "codebase-explainer", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-24T15:40:50Z", "size": 108},
    {"name": "notes-db", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-23T14:34:43Z", "size": 84},
    {"name": "langchain-rag", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-22T16:25:05Z", "size": 110},
    {"name": "rag-frontend", "description": None, "language": "HTML", "stargazers_count": 1, "updated_at": "2026-04-21T14:11:59Z", "size": 42},
    {"name": "chatbot-api", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-17T16:18:27Z", "size": 92},
    {"name": "search-api", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-15T14:51:35Z", "size": 74},
    {"name": "SmartGrocer", "description": "AI-powered grocery assistant that tracks inventory, reminds you of expiring items, and generates meal plans using Gemini.", "language": "Python", "stargazers_count": 0, "updated_at": "2026-04-09T14:55:18Z", "size": 165},
    {"name": "simple-api", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-06T13:47:58Z", "size": 60},
    {"name": "Notes-api", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-06T13:47:57Z", "size": 59},
    {"name": "LLM-basics", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-06T13:47:51Z", "size": 80},
    {"name": "rag-basics", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-06T13:47:47Z", "size": 76},
    {"name": "rag-api", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-06T13:47:44Z", "size": 88},
    {"name": "sentiment-analysis", "description": None, "language": "Python", "stargazers_count": 1, "updated_at": "2026-04-06T13:47:13Z", "size": 72},
    {"name": "SCT_ML_03", "description": "Streamlit app: upload an image to classify cat vs dog using MobileNetV2 features and an SVM", "language": "Jupyter Notebook", "stargazers_count": 0, "updated_at": "2025-08-05T14:53:35Z", "size": 190},
    {"name": "SCT_ML_04", "description": "Real-time hand gesture recognition using a trained Keras model on 64x64 grayscale images via webcam.", "language": "Jupyter Notebook", "stargazers_count": 0, "updated_at": "2025-08-05T14:52:53Z", "size": 176},
    {"name": "SCT_ML_02", "description": "Interactive Streamlit app for customer segmentation using K-Means clustering.", "language": "Python", "stargazers_count": 0, "updated_at": "2025-08-03T13:03:44Z", "size": 128},
    {"name": "SCT_ML_01", "description": "Simple linear regression model to predict house prices using living area, bedrooms, and bathrooms.", "language": "Jupyter Notebook", "stargazers_count": 0, "updated_at": "2025-08-03T13:02:04Z", "size": 150},
]


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
    try:
        return get_json(f"https://api.github.com/users/{LOGIN}")
    except HTTPError:
        return FALLBACK_PROFILE.copy()


def fetch_repositories() -> list[dict]:
    repos: list[dict] = []
    page = 1
    try:
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
    except HTTPError:
        return [repo.copy() for repo in FALLBACK_REPOS]
    return repos


def normalize_language(language: str | None) -> str | None:
    if language is None:
        return None
    if language == "Jupyter Notebook":
        return "Python"
    return language


def fetch_languages(repositories: list[dict]) -> tuple[Counter, Counter]:
    language_bytes: Counter[str] = Counter()
    repo_counts: Counter[str] = Counter()
    for repo in repositories:
        primary = normalize_language(repo.get("language"))
        if primary:
            repo_counts[primary] += 1
            language_bytes[primary] += int(repo.get("size", 0)) * 1024
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        try:
            data = get_json(languages_url)
        except HTTPError:
            continue
        if isinstance(data, dict):
            if primary:
                language_bytes[primary] -= int(repo.get("size", 0)) * 1024
            for language, size in data.items():
                if isinstance(size, int):
                    language_bytes[normalize_language(language) or language] += size
    return language_bytes, repo_counts


def contribution_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=364), today


def fetch_owner_contributions(token: str, start: date, end: date) -> list[ContributionDay]:
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar {
              weeks {
                contributionDays {
                  date
                  contributionCount
                }
              }
            }
          }
        }
      }
    """
    payload = json.dumps(
        {
            "query": query,
            "variables": {
                "login": LOGIN,
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{end.isoformat()}T23:59:59Z",
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": f"{LOGIN}-profile-generator",
        },
    )
    with urllib.request.urlopen(request) as response:
        data = json.load(response)

    if data.get("errors"):
        raise RuntimeError("GitHub GraphQL could not read owner contribution data.")

    calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        ContributionDay(day=date.fromisoformat(item["date"]), count=int(item["contributionCount"]))
        for week in calendar["weeks"]
        for item in week["contributionDays"]
    ]
    if len(days) < 300:
        raise RuntimeError("GitHub GraphQL returned an incomplete contribution calendar.")
    return sorted(days, key=lambda item: item.day)


def parse_contribution_calendar(html: str) -> list[ContributionDay]:
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

    return days


def fetch_public_contribution_year(year: int) -> list[ContributionDay]:
    params = urllib.parse.urlencode({"from": f"{year}-01-01", "to": f"{year}-12-31"})
    html = get_text(f"https://github.com/users/{LOGIN}/contributions?{params}")
    return parse_contribution_calendar(html)


def fetch_contributions() -> list[ContributionDay]:
    start, end = contribution_window()
    owner_token = os.environ.get("PROFILE_TOKEN")
    if owner_token:
        try:
            return fetch_owner_contributions(owner_token, start, end)
        except (HTTPError, URLError, KeyError, RuntimeError) as error:
            print(f"Owner contribution data unavailable; using public data instead: {error}")

    # The public endpoint accepts one calendar year at a time; combine years before slicing.
    by_day: dict[date, ContributionDay] = {}
    for year in range(start.year, end.year + 1):
        for item in fetch_public_contribution_year(year):
            if start <= item.day <= end:
                by_day[item.day] = item
    days = sorted(by_day.values(), key=lambda item: item.day)

    if len(days) < 300:
        raise RuntimeError("Could not parse enough contribution days from GitHub.")

    return days


def compute_streaks(days: list[ContributionDay]) -> dict:
    longest_len = 0
    longest_start: date | None = None
    longest_end: date | None = None
    current_len = 0
    current_start: date | None = None
    active_days = 0
    week_totals: OrderedDict[date, int] = OrderedDict()

    run_len = 0
    run_start: date | None = None
    previous_day: date | None = None

    for item in days:
        week_start = item.day - timedelta(days=(item.day.weekday() + 1) % 7)
        week_totals.setdefault(week_start, 0)
        week_totals[week_start] += item.count

        if item.count > 0:
            active_days += 1
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

    current_days = days[:-1] if days and days[-1].day == date.today() and days[-1].count == 0 else days
    for item in reversed(current_days):
        if item.count > 0:
            current_len += 1
            current_start = item.day
        else:
            break

    active_weeks = sum(1 for total in week_totals.values() if total > 0)
    best_week = max(week_totals.values()) if week_totals else 0
    return {
        "longest_len": longest_len,
        "longest_start": longest_start,
        "longest_end": longest_end,
        "current_len": current_len,
        "current_start": current_start,
        "current_end": current_days[-1].day if current_len else None,
        "active_days": active_days,
        "active_weeks": active_weeks,
        "best_week": best_week,
        "week_totals": list(week_totals.items()),
    }


def fmt_short(value: date | None) -> str:
    if value is None:
        return "n/a"
    return f"{value.strftime('%b')} {value.day}"


def fmt_range(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return "n/a"
    return f"{fmt_short(start)} -> {fmt_short(end)}"


def total_stars(repositories: list[dict]) -> int:
    return sum(int(repo.get("stargazers_count", 0)) for repo in repositories)


def build_card(width: int, height: int, body: str, title: str, description: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(description)}</desc>
  <rect width="{width}" height="{height}" rx="12" fill="{BG}" />
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="11" fill="none" stroke="{EDGE}" />
  {body}
</svg>
"""


def sparkline(points: list[int], *, x: float, baseline: float, width: float, height: float) -> str:
    if not points:
        return ""
    max_value = max(points) or 1
    coords = []
    for index, value in enumerate(points):
        px = x + (index / max(1, len(points) - 1)) * width
        py = baseline - (value / max_value) * height
        coords.append(f"{px:.2f},{py:.2f}")
    return (
        f'<polyline fill="none" stroke="{TEXT}" stroke-width="2.8" stroke-linecap="round" '
        f'stroke-linejoin="round" opacity="0.92" points="{" ".join(coords)}" />'
        f'<circle cx="{x + width:.2f}" cy="{baseline - (points[-1] / max_value) * height:.2f}" r="4.5" fill="{TEXT}" />'
    )


def top_repositories(repositories: list[dict]) -> list[dict]:
    repos = [repo for repo in repositories if repo.get("name") != LOGIN]
    repos.sort(
        key=lambda repo: (
            int(repo.get("stargazers_count", 0)),
            repo.get("updated_at", ""),
        ),
        reverse=True,
    )
    return repos[:4]


def generate_hero_svg(profile: dict, repositories: list[dict], contributions: list[ContributionDay], streaks: dict) -> None:
    # A smaller grid keeps the complete cutout above the contribution metrics.
    rows = build_ascii_rows(cols=78)
    defs, portrait_group, portrait_width, portrait_height = render_ascii_layers(
        rows,
        x=0,
        y=0,
        font_size=10.4,
        char_width=6.2,
        line_height=11.5,
        color=TEXT,
        cursor_color=TEXT,
        animate=True,
    )

    width = 1100
    height = 760
    portrait_x = (width - portrait_width) / 2
    portrait_y = 76
    total = sum(item.count for item in contributions)
    weekly_totals = [value for _, value in streaks["week_totals"]]

    body = f"""
  <defs>{defs}
  </defs>
  <text x="28" y="48" fill="{TEXT}" font-size="17" font-family="{SANS}" font-weight="600">{LOGIN}</text>
  <text x="{28 + (len(LOGIN) * 10.4):.2f}" y="48" fill="{MUTED}" font-size="16" font-family="{MONO}">/ README.md</text>
  <g transform="translate({portrait_x:.2f},{portrait_y:.2f})">{portrait_group}</g>

  <text x="165" y="610" fill="{TEXT}" font-size="72" font-family="{SANS}" font-weight="700">{total}</text>
  <text x="165" y="650" fill="{MUTED}" font-size="18" font-family="{MONO}">contributions in the last year</text>

  <text x="910" y="604" text-anchor="end" fill="{TEXT}" font-size="28" font-family="{SANS}" font-weight="700">{streaks["active_days"]}</text>
  <text x="910" y="638" text-anchor="end" fill="{MUTED}" font-size="16" font-family="{MONO}">active days</text>
  <text x="910" y="694" text-anchor="end" fill="{TEXT}" font-size="28" font-family="{SANS}" font-weight="700">{streaks["best_week"]}</text>
  <text x="910" y="728" text-anchor="end" fill="{MUTED}" font-size="16" font-family="{MONO}">best week</text>

  <line x1="165" y1="705" x2="912" y2="705" stroke="{EDGE}" />
  {sparkline(weekly_totals, x=165, baseline=705, width=747, height=68)}
"""

    svg = build_card(
        width,
        height,
        body,
        f"GitHub profile hero for {profile.get('name') or LOGIN}",
        "An animated ASCII portrait with contribution totals and weekly sparkline.",
    )
    (OUTPUT_DIR / "hero.svg").write_text(svg, encoding="utf-8")


def generate_details_svg(repositories: list[dict], streaks: dict, contributions: list[ContributionDay], language_bytes: Counter, repo_counts: Counter) -> None:
    width = 1100
    height = 700
    last_active = next((item.day for item in reversed(contributions) if item.count > 0), None)

    top_bytes = language_bytes.most_common(5)
    total_bytes = sum(language_bytes.values()) or 1
    max_bytes = top_bytes[0][1] if top_bytes else 1

    bars: list[str] = []
    for index, (language, value) in enumerate(top_bytes):
        y = 228 + index * 48
        label = language.lower()
        percentage = value / total_bytes * 100
        bar_width = 300 * (value / max_bytes)
        bars.append(
            f'<text x="195" y="{y}" fill="{TEXT}" font-size="18" font-family="{MONO}" font-weight="600">{escape(label)}</text>'
            f'<rect x="452" y="{y - 11}" width="300" height="12" rx="3" fill="{EDGE}" />'
            f'<rect x="452" y="{y - 11}" width="{bar_width:.2f}" height="12" rx="3" fill="{TEXT}" opacity="0.9" />'
            f'<text x="778" y="{y}" fill="{MUTED}" font-size="16" font-family="{MONO}">{percentage:.0f}%</text>'
        )

    repo_lines: list[str] = []
    for index, (language, count) in enumerate(repo_counts.most_common(5)):
        y = 228 + index * 48
        repo_width = min(66, 20 + count * 7)
        repo_lines.append(
            f'<text x="850" y="{y}" fill="{TEXT}" font-size="18" font-family="{MONO}" font-weight="600">{escape(language.lower())}</text>'
            f'<rect x="982" y="{y - 11}" width="{repo_width}" height="12" rx="3" fill="{TEXT}" opacity="0.85" />'
            f'<text x="1080" y="{y}" fill="{MUTED}" font-size="16" text-anchor="end" font-family="{MONO}">{count}</text>'
        )

    counts = [item.count for item in contributions]
    max_count = max(counts) if counts else 1
    weeks: OrderedDict[date, list[str]] = OrderedDict()
    for item in contributions:
        week_start = item.day - timedelta(days=(item.day.weekday() + 1) % 7)
        weeks.setdefault(week_start, [" "] * 7)
        day_index = (item.day.weekday() + 1) % 7
        glyph_index = 0 if item.count == 0 else max(1, round((item.count / max_count) * (len(YEAR_RAMP) - 1)))
        weeks[week_start][day_index] = YEAR_RAMP[glyph_index]

    heat_rows = []
    labels = {1: "mon", 3: "wed", 5: "fri"}
    for row_index in range(7):
        row = "".join(column[row_index] for column in weeks.values())
        label = labels.get(row_index, "   ")
        heat_rows.append((label, row))

    month_marks: list[str] = []
    seen_months: set[str] = set()
    start_x = 194
    for col_index, week_start in enumerate(weeks.keys()):
        label = week_start.strftime("%b").lower()
        if label in seen_months:
            continue
        seen_months.add(label)
        month_marks.append(
            f'<text x="{start_x + col_index * 13.4:.2f}" y="482" fill="{MUTED}" font-size="14" font-family="{MONO}">{label}</text>'
        )

    heat_text = []
    for row_index, (label, row) in enumerate(heat_rows):
        y = 534 + row_index * 22
        heat_text.append(
            f'<text x="144" y="{y}" fill="{MUTED}" font-size="14" font-family="{MONO}">{label}</text>'
            f'<text x="{start_x}" y="{y}" fill="{TEXT}" font-size="14" font-family="{MONO}" xml:space="preserve">{escape(row)}</text>'
        )

    body = f"""
  <text x="188" y="94" fill="{TEXT}" font-size="42" font-family="{SANS}" font-weight="700">{streaks["current_len"]}</text>
  <text x="188" y="122" fill="{MUTED}" font-size="16" font-family="{MONO}">current streak</text>
  <text x="188" y="150" fill="{MUTED}" font-size="16" font-family="{MONO}">{escape(fmt_range(streaks["current_start"], streaks["current_end"])) if streaks["current_len"] else "last active " + escape(f"{last_active.strftime('%b')} {last_active.day}, {last_active.year}" if last_active else "n/a")}</text>

  <line x1="530" y1="62" x2="530" y2="150" stroke="{EDGE}" />

  <text x="576" y="94" fill="{TEXT}" font-size="42" font-family="{SANS}" font-weight="700">{streaks["longest_len"]}</text>
  <text x="576" y="122" fill="{MUTED}" font-size="16" font-family="{MONO}">longest streak</text>
  <text x="576" y="150" fill="{MUTED}" font-size="16" font-family="{MONO}">{escape(fmt_range(streaks["longest_start"], streaks["longest_end"]))}</text>

  <text x="188" y="196" fill="{MUTED}" font-size="14" font-family="{MONO}" letter-spacing="1">BY BYTES</text>
  <text x="870" y="196" fill="{MUTED}" font-size="14" font-family="{MONO}" letter-spacing="1">BY REPOS</text>
  {''.join(bars)}
  {''.join(repo_lines)}

  <text x="188" y="438" fill="{MUTED}" font-size="14" font-family="{MONO}" letter-spacing="1">THE YEAR</text>
  <text x="188" y="462" fill="{MUTED}" font-size="14" font-family="{MONO}">{streaks["active_days"]} of 365 days had a contribution</text>
  <text x="888" y="462" fill="{MUTED}" font-size="14" font-family="{MONO}">less  {YEAR_RAMP[0]} {YEAR_RAMP[1]} {YEAR_RAMP[2]} {YEAR_RAMP[3]} {YEAR_RAMP[4]} {YEAR_RAMP[5]}  more</text>
  {''.join(month_marks)}
  {''.join(heat_text)}
"""

    svg = build_card(
        width,
        height,
        body,
        f"GitHub detail stats for {LOGIN}",
        "A self-hosted panel showing streaks, language usage, and a one-character-per-day contribution map.",
    )
    (OUTPUT_DIR / "details.svg").write_text(svg, encoding="utf-8")


def cleanup_old_assets() -> None:
    for name in ("stats.svg", "streak.svg", "langs.svg", "year.svg"):
        path = OUTPUT_DIR / name
        if path.exists():
            path.unlink()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile = fetch_profile()
    repositories = fetch_repositories()
    contributions = fetch_contributions()
    streaks = compute_streaks(contributions)
    language_bytes, repo_counts = fetch_languages(repositories)

    generate_hero_svg(profile, repositories, contributions, streaks)
    generate_details_svg(repositories, streaks, contributions, language_bytes, repo_counts)
    cleanup_old_assets()

    metadata = {
        "login": LOGIN,
        "name": profile.get("name"),
        "public_repos": profile.get("public_repos"),
        "followers": profile.get("followers"),
        "stars": total_stars(repositories),
        "featured_projects": [
            {
                "name": repo.get("name"),
                "description": repo.get("description"),
                "language": normalize_language(repo.get("language")),
            }
            for repo in top_repositories(repositories)
        ],
    }
    (OUTPUT_DIR / "profile-data.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote generated stats for {LOGIN}")


if __name__ == "__main__":
    main()
