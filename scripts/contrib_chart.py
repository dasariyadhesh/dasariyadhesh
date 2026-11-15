"""Draw GitHub contribution totals and a contribution-type donut as light and dark SVG cards.

Shows contributions and active days for the last 12 months, plus a donut of
contribution types (private work, commits, pull requests, other). Private work
is included as anonymous counts when "Include private contributions" is on.
Writes assets/contrib-light.svg and assets/contrib-dark.svg.

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
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}"""

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'Cascadia Mono', Consolas, Menlo, monospace"

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
    return body["data"]["user"]["contributionsCollection"]



# Contribution types, in a fixed order with fixed colours (validated categorical
# slots 1-4 from the dataviz reference palette). Colour follows the type, never rank.
TYPES = [
    ("Private work", {"light": "#2a78d6", "dark": "#3987e5"}),
    ("Commits", {"light": "#eb6834", "dark": "#d95926"}),
    ("Pull requests", {"light": "#1baf7a", "dark": "#199e70"}),
    ("Other", {"light": "#eda100", "dark": "#c98500"}),
]


def breakdown(cc):
    total = cc["contributionCalendar"]["totalContributions"]
    private = cc["restrictedContributionsCount"]
    commits = cc["totalCommitContributions"]
    prs = cc["totalPullRequestContributions"]
    other = max(total - private - commits - prs, 0)  # issues, reviews, new repos
    return total, [private, commits, prs, other]


def donut(cx, cy, r, width, values, theme, t):
    import math
    total = sum(values) or 1
    parts, start = [], -math.pi / 2
    for (name, colours), v in zip(TYPES, values):
        if not v:
            continue
        sweep = 2 * math.pi * v / total
        end = start + sweep
        if sweep >= 2 * math.pi - 1e-6:  # a single type fills the ring
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r - width / 2}" fill="none" stroke="{colours[theme]}" '
                         f'stroke-width="{width}"><title>{name}: {v}</title></circle>')
        else:
            ro, ri = r, r - width
            large = 1 if sweep > math.pi else 0
            x1, y1 = cx + ro * math.cos(start), cy + ro * math.sin(start)
            x2, y2 = cx + ro * math.cos(end), cy + ro * math.sin(end)
            x3, y3 = cx + ri * math.cos(end), cy + ri * math.sin(end)
            x4, y4 = cx + ri * math.cos(start), cy + ri * math.sin(start)
            d = (f"M{x1:.2f},{y1:.2f} A{ro},{ro} 0 {large} 1 {x2:.2f},{y2:.2f} "
                 f"L{x3:.2f},{y3:.2f} A{ri},{ri} 0 {large} 0 {x4:.2f},{y4:.2f} Z")
            # 2px surface-coloured stroke = the gap between neighbouring slices
            parts.append(f'<path d="{d}" fill="{colours[theme]}" stroke="{t["bg"]}" stroke-width="2">'
                         f'<title>{name}: {v} ({100 * v / total:.0f}%)</title></path>')
        start = end
    return "".join(parts)


def summary_svg(cc, t, theme):
    """Contributions and active days, plus a donut of contribution types."""
    cal = cc["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    active = sum(1 for d in days if d["contributionCount"])
    total, values = breakdown(cc)
    W, H = 920, 200
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="{total} contributions and {active} active days in the last 12 months; '
         + "; ".join(f"{n}: {v}" for (n, _), v in zip(TYPES, values)) + '">',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{t["bg"]}" stroke="{t["line"]}"/>',
         f'<text x="32" y="40" font-family="{MONO}" font-size="12" font-weight="600" fill="{t["muted"]}" '
         f'letter-spacing="1.2">LAST 12 MONTHS ON GITHUB</text>']

    # Two headline figures
    x = 32
    for val, lab in ((f"{total:,}", "contributions"), (f"{active:,}", "active days")):
        p.append(f'<text x="{x}" y="108" font-family="{SANS}" font-size="44" font-weight="800" fill="{t["ink"]}">{escape(val)}</text>')
        p.append(f'<text x="{x}" y="132" font-family="{MONO}" font-size="12" fill="{t["muted"]}">{escape(lab)}</text>')
        x += 190
    p.append(f'<line x1="400" y1="36" x2="400" y2="164" stroke="{t["line"]}"/>')

    # Donut of contribution types, legend with direct values beside it
    cx, cy = 500, 104
    p.append(donut(cx, cy, 62, 20, values, theme, t))
    p.append(f'<text x="{cx}" y="{cy + 2}" font-family="{SANS}" font-size="20" font-weight="700" fill="{t["ink"]}" '
             f'text-anchor="middle">{total:,}</text>')
    p.append(f'<text x="{cx}" y="{cy + 18}" font-family="{MONO}" font-size="10" fill="{t["muted"]}" text-anchor="middle">total</text>')
    ly = 62
    shown = [(n, c, v) for (n, c), v in zip(TYPES, values) if v]
    for name, colours, v in shown:
        p.append(f'<rect x="604" y="{ly - 10}" width="12" height="12" rx="3" fill="{colours[theme]}"/>')
        p.append(f'<text x="626" y="{ly}" font-family="{SANS}" font-size="14" fill="{t["ink"]}">{escape(name)}</text>')
        p.append(f'<text x="830" y="{ly}" font-family="{SANS}" font-size="14" font-weight="600" fill="{t["ink"]}" '
                 f'text-anchor="end">{v:,}</text>')
        p.append(f'<text x="888" y="{ly}" font-family="{MONO}" font-size="12" fill="{t["muted"]}" text-anchor="end">'
                 f'{100 * v / (total or 1):.0f}%</text>')
        ly += 28
    p.append(f'<text x="32" y="176" font-family="{MONO}" font-size="11" fill="{t["muted"]}">'
             f'updated {date.today().strftime("%d %b %Y")} · private work counted without repo names</text>')
    p.append("</svg>")
    return "".join(p)



def main():
    cc = fetch(LOGIN)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        (OUT / f"contrib-{name}.svg").write_text(summary_svg(cc, t, name), encoding="utf-8")
    total, values = breakdown(cc)
    print(f"{total} contributions {values} -> {OUT}/contrib-{{light,dark}}.svg")


if __name__ == "__main__":
    main()
