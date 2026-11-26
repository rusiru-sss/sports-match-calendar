# Sports Match Intelligence

Static dashboard with a rolling **current month and next month** fixture table.

## Features
- Today, Next 7 Days, Entire Month, and Next Month tabs
- Search, sport and promotion filters, Sri Lanka-local times, CSV export
- Automated data refresh every 6 hours using GitHub Actions
- Static deployment to GitHub Pages after a refresh

## Publish
1. Merge the deployment pull request into `main`.
2. In **Settings > Pages**, set **Source** to **GitHub Actions**.
3. In **Actions > Refresh match inventory and deploy site**, choose **Run workflow**.
4. The site should appear at `https://rusiru-sss.github.io/sports-match-calendar/` when the deployment succeeds.

The repository is **private**. Check your plan's GitHub Pages eligibility; alternatively make a public mirror of the non-sensitive site content. The site and exported data are publicly accessible once published.

## Feed and limitations
`scripts/build_matches.py` retrieves two rolling calendar months via the TheSportsDB daily public API, normalizes and deduplicates entries, and writes `data/matches.json` as part of each deployment. The free API is **limited coverage**, not a complete fixture inventory. Some sports/months may have few or zero events. For broader coverage, integrate a licensed feed or a compatible premium TheSportsDB key using repository secret `SPORTSDB_API_KEY`. No events are fabricated. Dates without confirmed event times are displayed as TBD.

The prior README mentioned a multi-provider scraper and an Actions workflow, but neither existed in the original repository. This version supplies a working baseline, not guaranteed comprehensive match coverage.
