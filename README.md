# Sports Match Intelligence

A static Sri Lanka-time sports calendar for the current **and next month**, with country flags for recognized international fixtures and a separate bonus policy draft register.

## Free fixture fallback (no API keys)

The daily collector `scripts/fallback_feeds.py` loads multiple sources and deduplicates overlapping entries. A failure in one source does not prevent other sources from producing events.

| Source | Role | Limitations |
| --- | --- | --- |
| [Sporting Events](https://sporting-events.org/data/) | Downloadable sport category JSON, including football/cricket/rugby/F1 | Some listings represent competitions rather than individual matches; free with attribution |
| [SportsEvents24](https://sportsevents24.com/api) | Cricket, soccer, rugby, basketball | Only next 30 days; 100 requests/day, 5,000 records/month, 100 records/page; queried conservatively |
| [OpenLigaDB](https://www.openligadb.de/) | German football leagues | Not worldwide; database license ODbL |
| [Jolpica F1](https://github.com/jolpica/jolpica-f1) | Formula 1 season schedules | F1 race events only |
| ESPN public scoreboard | Additional competition coverage | Unofficial endpoints may change or refuse requests |
| TheSportsDB public endpoint | Short-range fallback | Limited coverage and requests may fail |
| Last successful deployed snapshot | Fallback when providers fail | Stale entries are **not** new fixtures |

Coverage is **not guaranteed** for any sport/month. Never interpret a provider returning zero fixtures as confirmation that there are no scheduled matches.

## Automation
The GitHub Actions workflow runs once daily (03:27 UTC) and on push to main. It verifies Python syntax, fetches fixtures, then deploys the dashboard to GitHub Pages. If zero valid fixtures remain even after checking the last published snapshot, deployment aborts rather than overwriting it with empty data. A provider warning is surfaced on the dashboard; provider metadata is written in `data/matches.json`.

SportsEvents24 allows date ranges only through 30 days ahead; another source must supply fixtures later in next month. We intentionally use fewer requests than the daily public allowance and avoid polling it every six hours.

## GitHub Pages
Configure **Settings > Pages > Source: GitHub Actions**; merge this branch into main. The site is deployed at https://rusiru-sss.github.io/sports-match-calendar/.

## Legal / editorial
Respect each feed's access terms and licensing for business use. Data from [Sporting Events](https://sporting-events.org/data/) requires attribution; displayed here and on the dashboard. OpenLigaDB data is offered under ODbL. Public ESPN or other unofficial endpoints do not promise availability or redistribute rights. This is a schedule-planning aid, not a source of live betting odds or guaranteed complete fixtures.

The public `bonus-policy.html` page is **draft documentation only**. Do not include confidential promotional terms or customer details until the site is access protected.
