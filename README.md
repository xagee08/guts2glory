# Guts2Glory — League History

Free, self-updating league history site. No hosting bill, no expiring site, no dashboard uploads.

**Stack:** GitHub Pages (hosting, $0) + GitHub Actions (automation, $0 on public repos) + ESPN API.

---

## What's in here

| File | What it is | Do you edit it? |
| --- | --- | --- |
| `index.html` | The site. Hand-written CSS + vanilla JS, zero external dependencies. | Only for design changes |
| `legacy.json` | Frozen 2018–2025 NFL.com history, extracted from `League History.xlsx`. | Once, to add `manager_map` |
| `data.json` | Generated. Legacy + current ESPN season merged. | **Never** — it gets overwritten |
| `update_league.py` | Pulls ESPN, merges, recomputes records and the all-time leaderboard. | No |
| `.github/workflows/update.yml` | Runs the script weekly and deploys to Pages. | Only to change the schedule |

The site reads `data.json` at load time. `legacy.json` exists separately because **ESPN has no record of your 2018–2025 seasons** — its API is season-scoped and only knows about leagues that existed on ESPN. Keeping history in its own version-controlled file means an ESPN API change can never destroy eight years of records.

---

## Setup (about 10 minutes, one time)

### 1. Create the repo

Make a **public** repo named `guts2glory` on GitHub. Public matters: GitHub Pages is only free on public repos, and Actions minutes are unlimited on public repos. Private would require a paid plan for both.

Upload `index.html`, `legacy.json`, `data.json`, `update_league.py`, `README.md`, and the `.github/` folder.

### 2. Turn on Pages

**Settings → Pages → Source → GitHub Actions.** Not "Deploy from a branch" — the included workflow handles deployment itself.

Your site goes live at `https://<username>.github.io/guts2glory/`.

### 3. Add your ESPN league ID

Find it in your ESPN league URL: `.../league?leagueId=`**`1234567`**

**Settings → Secrets and variables → Actions → Variables tab → New variable**
- Name: `ESPN_LEAGUE_ID`
- Value: your number

### 4. Authentication — pick one

**Option A (recommended): make the league publicly viewable.** In ESPN: League Settings → Basic Settings → Viewable by Public → Yes. No cookies, nothing to expire, nothing to maintain. The script auto-detects this.

**Option B: private league.** In Chrome, log into ESPN, then DevTools (F12) → Application → Cookies → `fantasy.espn.com`. Copy `espn_s2` and `SWID`. Add both under **Secrets** (not Variables) as `ESPN_S2` and `ESPN_SWID`.

These cookies expire eventually. If the Action starts failing with an auth error, re-grab them — that's the maintenance cost of going private.

### 5. Test it

**Actions → Update league history → Run workflow.** Check the log for the team count and top-scorer line.

---

## The one thing you must do before Week 1

ESPN gives you account names like `Christopher M.`, not the `Christopher` used since 2018. Left alone, the all-time leaderboard splits one person into two rows — Drako would show as two managers with one title each instead of one manager with two.

After your first successful run, read the manager names out of the log and fill in `manager_map` in `legacy.json`:

```json
"manager_map": {
  "Christopher M.": "Christopher",
  "Drako P": "Drako",
  "Michael J": "Michael"
}
```

Left side = exactly what ESPN returns. Right side = the name already in your history. Commit it once and it applies forever.

---

## Running it

**During the season:** nothing. The workflow runs Tuesdays at 9 AM Central, after Monday Night Football finalizes, and only during September–January. Need a mid-week refresh? Actions → Run workflow.

**At season's end**, record the champion — this is the only manual step all year:

```bash
python update_league.py --season 2026 --champion 2026 "Team Name" "Manager"
git add data.json && git commit -m "2026 champion" && git push
```

The team name must match ESPN exactly; the script pulls that team's record automatically. Pushing triggers a redeploy, and the champion appears in the hero card, the championship wall, and the all-time title count.

**Local preview:**

```bash
python -m http.server 8000   # then open localhost:8000
```

Opening `index.html` by double-clicking will show a load error — browsers block `fetch()` on `file://` URLs. That's expected, not a bug.

---

## Why GitHub Pages over the alternatives

| | Free tier reality |
| --- | --- |
| **GitHub Pages** | 1 GB site, 100 GB/month bandwidth, both soft limits. Free forever on public repos. Custom domain free. Actions unlimited on public repos. |
| Cloudflare Pages | Also excellent — unlimited bandwidth, 500 builds/month. Needs a Cloudflare account, and you'd still use GitHub Actions to fetch ESPN. |
| tiiny.host free | Site is **deleted after 7 days**. Non-starter for a season-long site. |
| Netlify / Vercel | Fine free tiers, but bandwidth-metered and the free terms shift more often. |

Your site is roughly 55 KB total. You will never approach any of these limits.

---

## Troubleshooting

**Site loads but shows the data.json error.** Pages Source isn't set to "GitHub Actions", or the deploy job failed. Check the Actions log.

**Workflow fails: `Private league` / 401.** Cookies missing or expired. Re-grab them, or make the league public.

**A manager appears twice in All-Time Leaders.** `manager_map` needs that ESPN name added.

**Standings look stale.** The Action commits only when `data.json` actually changes. If ESPN hasn't finalized the week, there's nothing to commit — that's correct behavior.

**Changes don't show up.** Hard-refresh. The page already cache-busts `data.json` with a timestamp, but `index.html` itself can be cached by your browser.

---

## Current records (from the workbook)

- **8 seasons**, 2018–2025, 12 teams
- **Most titles:** Drako and Michael, 2 each
- **Best all-time win rate:** Christopher, .624 (68–41) with 5 podium finishes and 1 ring
- **Top single-player game:** T. Hill, 57.90 — 2020 Week 12, The Pantheon
- **Top single-week team:** Metairie BreEAZY (Drako), 234.32 — 2022 Week 2
- **Top season:** The Pantheon (Christopher), 1955.10 — 2021
