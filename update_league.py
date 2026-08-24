#!/usr/bin/env python3
"""
Guts2Glory league history updater.

Reads legacy.json (frozen 2018-2025 NFL.com history), optionally pulls the
current season from ESPN, merges the two, and writes data.json for index.html.

Usage:
    python update_league.py                 # legacy only (no ESPN call)
    python update_league.py --season 2026   # legacy + ESPN 2026

Env vars (set as GitHub Actions secrets for a private league):
    ESPN_LEAGUE_ID, ESPN_S2, ESPN_SWID
Public leagues need no cookies -- leave ESPN_S2 / ESPN_SWID unset.
"""

import argparse
import collections
import datetime
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
LEGACY = HERE / "legacy.json"
OUT = HERE / "data.json"


# --------------------------------------------------------------------------- #
# ESPN
# --------------------------------------------------------------------------- #
def fetch_espn(season, league_id, s2=None, swid=None):
    """Return (standings, hof_player, hof_week, hof_season) for one ESPN season."""
    from espn_api.football import League

    kwargs = {"league_id": int(league_id), "year": int(season)}
    if s2 and swid:
        kwargs.update(espn_s2=s2, swid=swid)
    lg = League(**kwargs)

    def owner_of(team):
        # ESPN's owner field shape has changed across library versions.
        o = getattr(team, "owners", None)
        if isinstance(o, list) and o:
            first = o[0]
            if isinstance(first, dict):
                return f"{first.get('firstName','')} {first.get('lastName','')}".strip()
            return str(first).strip()
        return str(getattr(team, "owner", "") or "").strip()

    standings = []
    for rank, t in enumerate(lg.standings(), 1):
        standings.append({
            "rank": rank,
            "team": t.team_name,
            "manager": owner_of(t),
            "record": f"{t.wins}-{t.losses}" + (f"-{t.ties}" if getattr(t, "ties", 0) else ""),
            "points": round(float(t.points_for), 2),
        })

    best_player = None   # top single-player game
    best_week = None     # top single-week team score

    # Only walk weeks that have actually been played.
    played = min(int(getattr(lg, "current_week", 1)) - 1,
                 int(lg.settings.reg_season_count))
    for wk in range(1, max(played, 0) + 1):
        try:
            boxes = lg.box_scores(wk)
        except Exception as exc:                      # noqa: BLE001
            print(f"  week {wk}: skipped ({exc})", file=sys.stderr)
            continue
        for box in boxes:
            for side, team in (("home", box.home_team), ("away", box.away_team)):
                if not team or isinstance(team, int):
                    continue
                score = float(getattr(box, f"{side}_score", 0) or 0)
                if score and (best_week is None or score > best_week["points"]):
                    best_week = {"year": int(season), "team": team.team_name,
                                 "manager": owner_of(team), "week": wk,
                                 "points": round(score, 2)}
                for p in getattr(box, f"{side}_lineup", []) or []:
                    if getattr(p, "slot_position", "") in ("BE", "IR"):
                        continue
                    pts = float(getattr(p, "points", 0) or 0)
                    if best_player is None or pts > best_player["points"]:
                        best_player = {
                            "year": int(season), "player": p.name,
                            "pos": f"{getattr(p,'position','')} - {getattr(p,'proTeam','')}",
                            "team": team.team_name, "week": wk, "points": round(pts, 2),
                        }

    top_season = max(standings, key=lambda r: r["points"]) if standings else None
    hof_season = ({"year": int(season), "team": top_season["team"],
                   "manager": top_season["manager"], "points": top_season["points"]}
                  if top_season else None)

    return standings, best_player, best_week, hof_season


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #
def wl(record):
    parts = record.split("-")
    return int(parts[0]), int(parts[1])


def recompute_all_time(data):
    titles = collections.Counter(c["manager"] for c in data["champions"])
    podiums = collections.Counter()
    for rows in data["final_standings"].values():
        for t in rows:
            if t["rank"] <= 3:
                podiums[t["manager"]] += 1

    agg = collections.defaultdict(lambda: {"w": 0, "l": 0, "seasons": 0, "points": 0.0})
    for rows in data["regular_season"].values():
        for t in rows:
            try:
                w, l = wl(t["record"])
            except (ValueError, IndexError):
                continue
            a = agg[t["manager"]]
            a["w"] += w
            a["l"] += l
            a["seasons"] += 1
            a["points"] += float(t.get("points") or 0)

    out = []
    for m, a in agg.items():
        g = a["w"] + a["l"]
        out.append({
            "manager": m, "seasons": a["seasons"], "wins": a["w"], "losses": a["l"],
            "pct": round(a["w"] / g, 3) if g else 0,
            "points": round(a["points"], 1),
            "ppg": round(a["points"] / g, 1) if g else 0,
            "titles": titles.get(m, 0), "podiums": podiums.get(m, 0),
        })
    out.sort(key=lambda x: (-x["titles"], -x["podiums"], -x["pct"]))
    return out


def upsert(rows, entry, key="year"):
    """Replace the row for entry[key], else append. Keeps list newest-first."""
    if entry is None:
        return rows
    rows = [r for r in rows if r.get(key) != entry.get(key)]
    rows.append(entry)
    rows.sort(key=lambda r: r[key], reverse=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, help="ESPN season to pull (e.g. 2026)")
    ap.add_argument("--champion", nargs=3, metavar=("YEAR", "TEAM", "MANAGER"),
                    help="Record a champion at season's end")
    args = ap.parse_args()

    data = json.loads(LEGACY.read_text())
    data.setdefault("manager_map", {})
    name_map = data["manager_map"]

    if args.season:
        league_id = os.environ.get("ESPN_LEAGUE_ID")
        if not league_id:
            sys.exit("ESPN_LEAGUE_ID is not set.")
        print(f"Fetching ESPN season {args.season} (league {league_id})...")
        standings, hp, hw, hs = fetch_espn(
            args.season, league_id,
            os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID"),
        )

        # Normalise ESPN account names to the display names used since 2018.
        def canon(x):
            return name_map.get(x, x)

        for r in standings:
            r["manager"] = canon(r["manager"])
        for rec in (hp, hw, hs):
            if rec and "manager" in rec:
                rec["manager"] = canon(rec["manager"])

        y = str(args.season)
        data["regular_season"][y] = standings
        # Final standings mirror regular season until the champion is recorded.
        data["final_standings"].setdefault(y, standings)

        H = data["hall_of_fame"]
        H["single_game_player"] = upsert(H["single_game_player"], hp)
        H["single_week_team"] = upsert(H["single_week_team"], hw)
        H["season_points"] = upsert(H["season_points"], hs)
        print(f"  {len(standings)} teams · top player {hp['points'] if hp else '—'} "
              f"· top week {hw['points'] if hw else '—'}")

    if args.champion:
        yr, team, mgr = args.champion
        rec = ""
        for r in data["regular_season"].get(yr, []):
            if r["team"] == team:
                rec = r["record"]
        data["champions"] = [c for c in data["champions"] if c["year"] != int(yr)]
        data["champions"].append({"year": int(yr), "team": team,
                                  "manager": mgr, "record": rec})
        data["champions"].sort(key=lambda c: c["year"], reverse=True)
        print(f"Champion recorded: {yr} {team} ({mgr})")

    data["all_time"] = recompute_all_time(data)
    data["generated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    OUT.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUT} · {len(data['regular_season'])} seasons · "
          f"{len(data['all_time'])} managers")


if __name__ == "__main__":
    main()
