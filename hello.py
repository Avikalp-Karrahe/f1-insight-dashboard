# hello.py
from preswald import sidebar, text, selectbox, alert, plotly, separator
from preswald import connect, get_df
import pandas as pd
import plotly.express as px
from functools import lru_cache

# ───────────────────────────────────────────────────────────────────────────────
# 1) DATA LOAD & PREP (runs once at import time)
# ───────────────────────────────────────────────────────────────────────────────
connect()

@lru_cache
def load_tables() -> dict[str, pd.DataFrame]:
    names = ["races", "lap_times", "results", "drivers", "circuits", "pit_stops"]
    tbls = {n: get_df(n) for n in names}
    # ensure correct types
    tbls["races"]["year"] = pd.to_numeric(tbls["races"]["year"], errors="coerce").astype(int)
    tbls["circuits"].rename(columns={"name": "circuitName"}, inplace=True)
    return tbls

T = load_tables()

@lru_cache
def make_master() -> pd.DataFrame:
    # Merge laps ⇢ drivers ⇢ races ⇢ circuits
    m = (
        T["lap_times"]
        .merge(T["drivers"][["driverId","driverRef"]], on="driverId")
        .merge(T["races"][["raceId","year","round","circuitId"]], on="raceId")
        .merge(T["circuits"][["circuitId","circuitName","lat","lng"]], on="circuitId")
    )
    # cast numeric
    m["lap"]          = pd.to_numeric(m["lap"], errors="coerce").astype(int)
    m["milliseconds"] = pd.to_numeric(m["milliseconds"], errors="coerce")
    m["lap_sec"]      = m["milliseconds"] / 1000
    return m

MASTER = make_master()

@lru_cache
def make_results() -> pd.DataFrame:
    # Merge results ⇢ drivers ⇢ races
    r = (
        T["results"]
        .merge(T["drivers"][["driverId","driverRef"]], on="driverId")
        .merge(T["races"][["raceId","year","round"]], on="raceId")
    )
    r["points"] = pd.to_numeric(r["points"], errors="coerce")
    return r

RESULTS = make_results()

# ───────────────────────────────────────────────────────────────────────────────
# 2) UI CONTROLS (runs on every interaction)
# ───────────────────────────────────────────────────────────────────────────────
sidebar(defaultopen=True)
text("# 🏁 F1 Deep-Dive Dashboard")

# Year selector
years  = sorted(MASTER["year"].unique().tolist(), reverse=True)
year   = selectbox("Select season", years, default=years[0])

# Driver selector
drivers = sorted(MASTER.loc[MASTER["year"] == year, "driverRef"].unique().tolist())
driver  = selectbox("Select driver", drivers, default=drivers[0])

# filter master once
df = MASTER[(MASTER["year"] == year) & (MASTER["driverRef"] == driver)]
if df.empty:
    alert(f"⚠️ No data for {driver.title()} in {year}", level="warning")
    raise SystemExit

separator()

# ───────────────────────────────────────────────────────────────────────────────
# 3) KPI CARDS
# ───────────────────────────────────────────────────────────────────────────────
fastest_lap = df["lap_sec"].min()
text(f"### ⚡ Fastest lap: **{fastest_lap:.3f} s**", size=0.33)

# avg pit-stop
pits = (
    T["pit_stops"]
    .merge(df[["raceId","driverId"]].drop_duplicates(), on=["raceId","driverId"])
)
pits["milliseconds"] = pd.to_numeric(pits["milliseconds"], errors="coerce")
avg_pit = pits["milliseconds"].mean() / 1000 if not pits.empty else None
text(
    f"### 🛠 Avg. pit-stop: **{avg_pit:.2f} s**"
    if avg_pit is not None else "### 🛠 Avg. pit-stop: **N/A**",
    size=0.33
)

# total points
pts = RESULTS[(RESULTS["year"]==year)&(RESULTS["driverRef"]==driver)]["points"].sum()
text(f"### 🏆 Points YTD: **{pts:.0f}**", size=0.33)

separator()

# ───────────────────────────────────────────────────────────────────────────────
# 4) Race-Pace: lap time line per circuit (colored)
# ───────────────────────────────────────────────────────────────────────────────
fig1 = px.line(
    df,
    x="lap", y="lap_sec",
    color="circuitName",
    labels={"lap_sec":"Lap time (s)"},
    title=f"{driver.title()} — Lap times by circuit in {year}"
)
for tr in fig1.data:
    tr.x, tr.y = list(tr.x), list(tr.y)
plotly(fig1)

# ───────────────────────────────────────────────────────────────────────────────
# 5) Lap-Time Distribution: histogram
# ───────────────────────────────────────────────────────────────────────────────
fig2 = px.histogram(
    df,
    x="lap_sec",
    nbins=50,
    title=f"{driver.title()} lap-time distribution ({year})",
    labels={"lap_sec":"Lap time (s)"}
)
plotly(fig2)

# ───────────────────────────────────────────────────────────────────────────────
# 6) Fastest Laps per Circuit: bar chart
# ───────────────────────────────────────────────────────────────────────────────
fastest_by_circ = (
    df.groupby("circuitName")["lap_sec"]
      .min()
      .reset_index()
      .sort_values("lap_sec")
)
fig3 = px.bar(
    fastest_by_circ,
    x="circuitName", y="lap_sec",
    title=f"Fastest lap per circuit — {driver.title()} {year}",
    labels={"lap_sec":"Fastest lap (s)"}
)
plotly(fig3)

# ───────────────────────────────────────────────────────────────────────────────
# 7) Pit-Stops Analysis: boxplot of pit durations
# ───────────────────────────────────────────────────────────────────────────────
text("## 🛠 Pit-Stops Analysis")
if pits.empty:
    alert("⚠️ No pit-stop data", level="warning")
else:
    pits["stop"] = pd.to_numeric(pits["stop"], errors="coerce").astype(int)
    fig4 = px.box(
        pits,
        x="stop", y=pits["milliseconds"]/1000,
        points="all",
        title=f"{driver.title()} pit-stop durations ({year})",
        labels={"y":"Pit stop (s)"}
    )
    for tr in fig4.data:
        if hasattr(tr, "y"): tr.y = list(tr.y)
    plotly(fig4)

# ───────────────────────────────────────────────────────────────────────────────
# 8) Points Progression: line over rounds
# ───────────────────────────────────────────────────────────────────────────────
text("## 🏆 Points Progression")
pts_df = RESULTS[(RESULTS["year"]==year)&(RESULTS["driverRef"]==driver)]
if pts_df.empty:
    alert("⚠️ No points data", level="warning")
else:
    pts_df = pts_df[["round","points"]].dropna().sort_values("round")
    fig5 = px.line(
        pts_df, x="round", y="points", markers=True,
        title=f"{driver.title()} points by round ({year})"
    )
    for tr in fig5.data:
        tr.x, tr.y = list(tr.x), list(tr.y)
    plotly(fig5)

# ───────────────────────────────────────────────────────────────────────────────
# 9) Circuit Map: where they raced
# ───────────────────────────────────────────────────────────────────────────────
text("## 🌍 Circuits Visited")
map_df = df[["circuitName","lat","lng"]].drop_duplicates()
map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
map_df["lng"] = pd.to_numeric(map_df["lng"], errors="coerce")
map_df = map_df.dropna(subset=["lat","lng"])
if map_df.empty:
    alert("⚠️ No location data", level="warning")
else:
    fig6 = px.scatter_mapbox(
        map_df, lat="lat", lon="lng",
        hover_name="circuitName",
        zoom=2, height=450,
        title=f"{driver.title()} circuits in {year}"
    )
    fig6.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":30,"l":0,"b":0})
    for tr in fig6.data:
        tr.lat, tr.lon = list(tr.lat), list(tr.lon)
    plotly(fig6)
