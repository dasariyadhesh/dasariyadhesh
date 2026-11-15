"""Draw the last year of GitHub contributions as light and dark SVG heatmaps.

Reads the public contribution calendar (private work is included as anonymous
counts when "Include private contributions" is on) and writes
assets/contrib-light.svg and assets/contrib-dark.svg.

Usage: GITHUB_TOKEN=... python scripts/contrib_chart.py [login] [out_dir]
Standard library only, so the GitHub Action needs no installs.
"""
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "dasariyadhesh"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "assets")

QUERY = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}"""

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'Cascadia Mono', Consolas, Menlo, monospace"
LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]

# One hue (the profile's teal), stepped light -> dark for magnitude.
# Dark mode is its own ramp: more contributions read as brighter on the dark surface.
THEMES = {
    "light": dict(bg="#f3f5f4", line="#d9e0dd", ink="#14201c", muted="#5a6763", accent="#0f6b5c",
                  ramp=["#e3e8e6", "#a8d5c9", "#5fae9c", "#2a8a76", "#0f5f51"]),
    "dark": dict(bg="#0f1513", line="#2a3531", ink="#e4ebe8", muted="#9aa8a3", accent="#5cc4ae",
                 ramp=["#1d2623", "#1d4a40", "#2b7564", "#45a68f", "#7fd9c3"]),
}


def fetch(login):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN to read the contribution calendar.")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-contrib-chart"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def stats(days):
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    current = 0
    # Today may still be empty; a streak counts through yesterday.
    tail = days[:-1] if days and not days[-1]["contributionCount"] else days
    for d in reversed(tail):
        if not d["contributionCount"]:
            break
        current += 1
    busiest = max(days, key=lambda d: d["contributionCount"])
    active = sum(1 for d in days if d["contributionCount"])
    return longest, current, busiest, active


def svg(cal, t):
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    longest, _current, busiest, _active = stats(days)

    cell, gap = 13, 3
    step = cell + gap
    left, top = 44, 96
    W = left + len(weeks) * step + 24
    H = top + 7 * step + 46

    bd = date.fromisoformat(busiest["date"])
    today = date.fromisoformat(days[-1]["date"])
    month_total = sum(d["contributionCount"] for d in days
                      if date.fromisoformat(d["date"]).replace(day=1) == today.replace(day=1))
    figures = [
        (f'{cal["totalContributions"]:,}', "contributions, last 12 months"),
        (f"{month_total:,}", f'in {today.strftime("%B %Y")}'),
        (f'{busiest["contributionCount"]}', f'busiest day · {bd.strftime("%d %b %Y")}'),
    ]

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="{cal["totalContributions"]} contributions in the last year; longest streak {longest} days">',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{t["bg"]}" stroke="{t["line"]}"/>']

    # Headline figures (text in ink tokens; the colour lives in the cells)
    x = left
    for i, (val, lab) in enumerate(figures):
        size = 26 if i == 0 else 18
        p.append(f'<text x="{x}" y="46" font-family="{SANS}" font-size="{size}" font-weight="700" fill="{t["ink"]}">{escape(val)}</text>')
        p.append(f'<text x="{x}" y="66" font-family="{MONO}" font-size="11" fill="{t["muted"]}">{escape(lab)}</text>')
        x += 240 if i == 0 else 170

    # Month labels, placed at the first week whose first day starts a new month
    last_month = None
    for wi, w in enumerate(weeks):
        first = date.fromisoformat(w["contributionDays"][0]["date"])
        if first.month != last_month and wi < len(weeks) - 2:
            if last_month is not None or first.day <= 7:
                p.append(f'<text x="{left + wi * step}" y="{top - 8}" font-family="{MONO}" font-size="11" '
                         f'fill="{t["muted"]}">{first.strftime("%b")}</text>')
            last_month = first.month

    # Weekday labels
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        p.append(f'<text x="{left - 8}" y="{top + row * step + 10}" font-family="{MONO}" font-size="10" '
                 f'fill="{t["muted"]}" text-anchor="end">{name}</text>')

    # Cells; the 3px gap is the surface showing through between fills
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            row = date.fromisoformat(d["date"]).isoweekday() % 7  # Sunday = 0
            lvl = LEVELS.index(d["contributionLevel"]) if d["contributionLevel"] in LEVELS else 0
            n = d["contributionCount"]
            p.append(f'<rect x="{left + wi * step}" y="{top + row * step}" width="{cell}" height="{cell}" rx="3" '
                     f'fill="{t["ramp"][lvl]}"><title>{n} contribution{"s" if n != 1 else ""} on {d["date"]}</title></rect>')

    # Legend: Less -> More
    ly = top + 7 * step + 22
    lx = W - 24 - (5 * step) - 74
    p.append(f'<text x="{lx}" y="{ly + 10}" font-family="{MONO}" font-size="11" fill="{t["muted"]}">Less</text>')
    for i, c in enumerate(t["ramp"]):
        p.append(f'<rect x="{lx + 34 + i * step}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{c}"/>')
    p.append(f'<text x="{lx + 38 + 5 * step}" y="{ly + 10}" font-family="{MONO}" font-size="11" fill="{t["muted"]}">More</text>')
    p.append(f'<text x="{left}" y="{ly + 10}" font-family="{MONO}" font-size="11" fill="{t["muted"]}">'
             f'Updated {date.today().strftime("%d %b %Y")} · includes private work as anonymous counts</text>')
    p.append("</svg>")
    return "".join(p)


def main():
    cal = fetch(LOGIN)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        (OUT / f"contrib-{name}.svg").write_text(svg(cal, t), encoding="utf-8")
    print(f'{cal["totalContributions"]} contributions -> {OUT}/contrib-{{light,dark}}.svg')


if __name__ == "__main__":
    main()
