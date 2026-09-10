# Rankings CSV format

Drop your own export in as `data/rankings.csv`. The loader is deliberately
forgiving: it re-maps common header names from Yahoo, ESPN, and FantasyPros
exports, and it ignores columns it does not recognize.

## Columns

Only `name` and `pos` are required. Everything else improves the advice.

| Column        | Required | What it does |
|---------------|----------|--------------|
| `rank`        | no       | **Your** overall ranking. This is the backbone of the value score. Without it, players are ranked in file order. |
| `name`        | **yes**  | Player name. Suffixes, punctuation, and nicknames are handled. |
| `pos`         | **yes**  | QB, RB, WR, TE, K, DEF (PK and D/ST are accepted). |
| `team`        | no       | NFL team abbreviation. Helps disambiguate same-surname players. |
| `bye`         | no       | Bye week. Shown on the board; used by Phase 2 bye-stacking. |
| `tier`        | no       | **Your** tiers. Drives every tier alert and cliff warning. If missing, tiers are derived automatically from ADP gaps. |
| `adp`         | no       | Average draft position. Drives survival odds. If missing, rank is used. |
| `adp_stdev`   | no       | Spread of ADP. Sharpens survival odds; a sensible default is assumed if absent. |
| `proj_points` | no       | Projected season points. Reserved for true per-league VORP. |
| `notes`       | no       | Free text, shown when you `find` a player. |
| `flags`       | no       | Keywords the engine reacts to: `injury`, `holdout`, `suspension`, `questionable` all reduce a player's score and show up in the reasoning. |

## Accepted header variants

`rank` also matches: rk, overall, overall rank, my rank, ovr
`name` also matches: player, player name, full name
`pos` also matches: position
`team` also matches: tm, nfl team, pro team
`adp` also matches: avg pick, average pick
`proj_points` also matches: proj, projection, projected points, fpts, points

## Example

```csv
rank,name,pos,team,bye,tier,adp,notes,flags
1,Jahmyr Gibbs,RB,DET,6,1,1.6,,
2,Bijan Robinson,RB,ATL,11,1,1.9,,
3,Puka Nacua,WR,LAR,11,1,3.1,elite target share,
4,Ja'Marr Chase,WR,CIN,6,1,3.9,,
```

## The current file

`data/rankings.csv` is currently **seeded from Fantasy Football Calculator's
free ADP API** (2026, 10-team PPR — the exact format of your league), with
tiers derived from ADP cliffs. It is a working placeholder, not a substitute
for your own research.

Refresh the seed at any time:

```bash
.venv/bin/python engine/adp.py
```

That overwrites `data/rankings.csv`, so **back up your own file first** if you
have replaced it with your rankings.
