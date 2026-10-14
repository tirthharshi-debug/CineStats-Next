"""
PDF Export Service - generates a colorful CineStats summary PDF.
Uses DARK text on WHITE background for maximum readability.
"""
from io import BytesIO
from datetime import datetime
import html
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# Colors (readable on white paper)
C_ROSE = "#c9184a"
C_TEAL = "#0d9488"
C_AMBER = "#b45309"
C_INDIGO = "#6d28d9"
C_CORAL = "#c2410c"
C_SKY = "#0369a1"
C_SAGE = "#15803d"
C_PLUM = "#7e22ce"
C_PINK = "#be185d"
C_GOLD = "#d97706"

H_ROSE = HexColor(C_ROSE)
H_TEAL = HexColor(C_TEAL)
H_INDIGO = HexColor(C_INDIGO)
H_CORAL = HexColor(C_CORAL)
H_SKY = HexColor(C_SKY)
H_SAGE = HexColor(C_SAGE)
H_PLUM = HexColor(C_PLUM)

TEXT_DARK = HexColor("#1a1a2e")
TEXT_MED = HexColor("#374151")
TEXT_LIGHT = HexColor("#6b7280")

ROW_BG = Color(0.97, 0.97, 0.99)
TABLE_LINE = Color(0.88, 0.88, 0.92)


def _esc(text):
    """Escape XML-sensitive characters for ReportLab Paragraphs."""
    return html.escape(str(text))


def _c(text, color_hex):
    """Wrap text in colored font tag (auto-escapes XML entities)."""
    return '<font color="' + color_hex + '">' + _esc(text) + '</font>'


def _build_styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("CT", parent=s["Title"], fontSize=28, textColor=H_INDIGO,
                         alignment=TA_CENTER, spaceAfter=2, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("CS", parent=s["Normal"], fontSize=11, textColor=TEXT_LIGHT,
                         alignment=TA_CENTER, spaceAfter=14))
    s.add(ParagraphStyle("SH", parent=s["Heading2"], fontSize=14, textColor=H_ROSE,
                         spaceAbove=16, spaceAfter=8, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("SH2", parent=s["Normal"], fontSize=11, textColor=H_INDIGO,
                         spaceAbove=10, spaceAfter=6, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("BD", parent=s["Normal"], fontSize=10, textColor=TEXT_DARK, spaceAfter=3))
    s.add(ParagraphStyle("SM", parent=s["Normal"], fontSize=9, textColor=TEXT_MED, spaceAfter=2))
    s.add(ParagraphStyle("MT", parent=s["Normal"], fontSize=8, textColor=TEXT_LIGHT, spaceAfter=2))
    return s


def _tbl(data, cw=None):
    """Styled table with alternating rows (auto-escapes cell text)."""
    safe_data = [[_esc(cell) for cell in row] for row in data]
    t = Table(safe_data, colWidths=cw or [220, 220])
    t.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_MED),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, TABLE_LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [Color(1, 1, 1), ROW_BG]),
    ]))
    return t


def generate_pdf(stats_data: dict) -> BytesIO:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    sty = _build_styles()
    story = []

    stats = stats_data.get("stats", {})
    basic = stats.get("basic", {})
    pro = stats.get("pro", {})
    patron = stats.get("patron", {})
    advanced = stats.get("advanced", {})
    community = stats.get("community_comparison", {})
    binge = stats.get("binge_stats", {})
    decades = stats.get("decade_leaderboard", [])
    monthly = stats.get("monthly_activity", [])

    ra = patron.get("runtime_analytics", {})
    da = patron.get("director_analytics", {})
    aa = patron.get("actor_analytics", {})
    ga = patron.get("genre_analytics", {})
    ca = patron.get("country_analytics", {})
    la = patron.get("language_analytics", {})

    # HEADER
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("CineStats Report", sty["CT"]))
    story.append(Paragraph("Your Cinematic Journey, Visualized", sty["CS"]))
    now_str = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    story.append(Paragraph("Generated on " + now_str, sty["MT"]))
    story.append(Spacer(1, 5*mm))

    # OVERVIEW
    story.append(Paragraph(_c("Overview", C_ROSE), sty["SH"]))
    ov = [
        ["Total Films", str(basic.get("total_films", 0))],
        ["Diary Entries", str(basic.get("total_diary_entries", 0))],
        ["Rewatches", str(basic.get("total_rewatches", 0))],
        ["Average Rating", "* " + str(basic.get("average_rating", 0))],
        ["Longest Streak", str(pro.get("longest_watch_streak", 0)) + " days"],
        ["Current Streak", str(pro.get("current_watch_streak", 0)) + " days"],
        ["Most Active Year", str(basic.get("most_active_year", "-"))],
        ["Most Active Month", str(basic.get("most_active_month", "-"))],
    ]
    if ra:
        hours = ra.get("total_runtime_hours", 0)
        days = ra.get("total_runtime_days", 0)
        ov.append(["Total Watch Time", str(hours) + "h (" + str(days) + "d)"])
        ov.append(["Average Runtime", str(ra.get("average_runtime", 0)) + " min"])
        lf = ra.get("longest_film")
        if lf:
            ov.append(["Longest Film", lf["title"] + " (" + str(lf["runtime"]) + "m)"])
        sf = ra.get("shortest_film")
        if sf:
            ov.append(["Shortest Film", sf["title"] + " (" + str(sf["runtime"]) + "m)"])
    fw = basic.get("first_watched")
    if fw:
        ov.append(["First Film", fw.get("title", "-")])
    mr = basic.get("most_recent_watched")
    if mr:
        ov.append(["Most Recent", mr.get("title", "-")])
    story.append(_tbl(ov))
    story.append(Spacer(1, 3*mm))

    # BINGE
    if binge and binge.get("multi_film_days", 0) > 0:
        story.append(Paragraph(_c("Binge Mode", C_CORAL), sty["SH"]))
        bd = [
            ["Multi-Film Days", str(binge.get("multi_film_days", 0))],
            ["Max Films in a Day", str(binge.get("max_films_in_day", 0))],
            ["Most Intense Day", str(binge.get("most_intense_day", "-"))],
            ["Avg Per Active Day", str(binge.get("avg_films_per_active_day", 0))],
        ]
        story.append(_tbl(bd))
        story.append(Spacer(1, 3*mm))

    # RATING DISTRIBUTION
    rd = basic.get("rating_distribution")
    if rd and isinstance(rd, dict):
        story.append(Paragraph(_c("Rating Distribution", C_AMBER), sty["SH"]))
        rd_rows = [["* " + str(k), str(v) + " films"]
                   for k, v in sorted(rd.items(), key=lambda x: float(x[0]))]
        story.append(_tbl(rd_rows, [120, 120]))
        story.append(Spacer(1, 3*mm))

    # GOLDEN ERAS
    if decades:
        story.append(Paragraph(_c("Golden Eras", C_GOLD), sty["SH"]))
        medals = ["1st", "2nd", "3rd", "4th", "5th"]
        for i, d in enumerate(decades[:5]):
            line = (medals[i] + " <b>" + _esc(d["decade"]) + "</b> - " +
                    _c("* " + str(d["avg_rating"]), C_GOLD) +
                    " (" + str(d["film_count"]) + " films)")
            story.append(Paragraph(line, sty["BD"]))
        story.append(Spacer(1, 3*mm))

    # YOU VS THE WORLD
    if community:
        story.append(Paragraph(_c("You vs The World", C_INDIGO), sty["SH"]))
        higher = community.get("rated_higher", [])[:5]
        lower = community.get("rated_lower", [])[:5]
        if higher:
            story.append(Paragraph(_c("You Loved More:", C_SAGE), sty["SH2"]))
            for f in higher:
                diff_val = f["difference"]
                diff_str = "+" + str(diff_val) if diff_val > 0 else str(diff_val)
                line = ("  * <b>" + _esc(f["title"]) + "</b> - You: " +
                        _c("*" + str(f["user_rating"]), C_GOLD) +
                        "  World: *" + str(f["tmdb_rating"]) +
                        "  " + _c("(" + diff_str + ")", C_SAGE))
                story.append(Paragraph(line, sty["SM"]))
        if lower:
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(_c("You Were Harsher:", C_ROSE), sty["SH2"]))
            for f in lower:
                line = ("  * <b>" + _esc(f["title"]) + "</b> - You: " +
                        _c("*" + str(f["user_rating"]), C_GOLD) +
                        "  World: *" + str(f["tmdb_rating"]) +
                        "  " + _c("(" + str(f["difference"]) + ")", C_ROSE))
                story.append(Paragraph(line, sty["SM"]))
        story.append(Spacer(1, 3*mm))

    # GENRES
    if ga:
        story.append(Paragraph(_c("Genres", C_PINK), sty["SH"]))
        gi = []
        mwg = ga.get("most_watched_genre")
        if mwg:
            gi.append(["Most Watched Genre", str(mwg)])
        fav = ga.get("favorite_genre")
        if fav:
            gi.append(["Favorite Genre", str(fav.get("name", "-")) + " (*" + str(fav.get("avg_rating", "-")) + ")"])
        gd = ga.get("genre_distribution")
        if gd:
            gi.append(["Genres Explored", str(len(gd))])
            if isinstance(gd, dict):
                top_g = sorted(gd.items(), key=lambda x: x[1], reverse=True)[:8]
                for name, count in top_g:
                    gi.append(["    " + name, str(count) + " films"])
        if gi:
            story.append(_tbl(gi))
        story.append(Spacer(1, 3*mm))

    # DIRECTORS
    if da:
        story.append(Paragraph(_c("Directors", C_INDIGO), sty["SH"]))
        di = []
        mwd = da.get("most_watched_director")
        if mwd:
            di.append(["Most Watched", str(mwd)])
        hrd = da.get("highest_rated_director")
        if hrd:
            di.append(["Highest Rated", str(hrd.get("name", "-")) + " (*" + str(hrd.get("avg_rating", "-")) + ")"])
        df = da.get("director_frequency")
        if df and isinstance(df, dict):
            td = sorted(df.items(), key=lambda x: x[1], reverse=True)[:8]
            for name, count in td:
                di.append(["    " + name, str(count) + " films"])
        if di:
            story.append(_tbl(di))
        dva = da.get("director_vs_average")
        if dva and isinstance(dva, dict):
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(_c("Director Ratings vs Average:", C_INDIGO), sty["SH2"]))
            items = list(dva.items())[:8]
            for name, info in items:
                d_val = info["diff"]
                d_str = "+" + str(d_val) if d_val >= 0 else str(d_val)
                d_color = C_SAGE if d_val >= 0 else C_ROSE
                line = ("  * " + _esc(name) + ": " +
                        _c("*" + str(info["avg"]), C_GOLD) + " " +
                        _c("(" + d_str + ")", d_color))
                story.append(Paragraph(line, sty["SM"]))
        story.append(Spacer(1, 3*mm))

    # ACTORS
    if aa and aa.get("top_10_actors"):
        story.append(Paragraph(_c("Top Actors", C_CORAL), sty["SH"]))
        for i, a in enumerate(aa["top_10_actors"][:10]):
            prefix = str(i + 1) + "."
            st = sty["BD"] if i < 3 else sty["SM"]
            line = prefix + " <b>" + _esc(a["name"]) + "</b> - " + _c(str(a["count"]) + " films", C_CORAL)
            story.append(Paragraph(line, st))
        story.append(Spacer(1, 3*mm))

    # WORLD CINEMA
    if ca or la:
        story.append(Paragraph(_c("World Cinema", C_SKY), sty["SH"]))
        wi = []
        if ca and ca.get("most_watched_country"):
            wi.append(["Top Country", str(ca["most_watched_country"])])
            cd_dict = ca.get("country_distribution", {})
            wi.append(["Countries Explored", str(len(cd_dict))])
        if la and la.get("most_watched_language"):
            wi.append(["Top Language", str(la["most_watched_language"])])
            ld_dict = la.get("language_distribution", {})
            wi.append(["Languages", str(len(ld_dict))])
        if ca and ca.get("country_distribution"):
            tc = sorted(ca["country_distribution"].items(), key=lambda x: x[1], reverse=True)[:6]
            for name, count in tc:
                wi.append(["    " + name, str(count)])
        if wi:
            story.append(_tbl(wi))
        story.append(Spacer(1, 3*mm))

    # MONTHLY ACTIVITY
    if monthly:
        story.append(Paragraph(_c("Monthly Activity", C_TEAL), sty["SH"]))
        for m in monthly[:6]:
            line = "<b>" + str(m["month"]) + " " + str(m["year"]) + "</b>: "
            line += _c(str(m["total_films"]) + " films", C_TEAL)
            ar = m.get("avg_rating")
            if ar:
                line += " - " + _c("*" + str(ar), C_GOLD)
            mf = m.get("max_films_in_day", 0)
            if mf >= 2:
                line += " (" + _c("Peak: " + str(mf) + " in a day", C_CORAL) + ")"
            story.append(Paragraph(line, sty["SM"]))
        story.append(Spacer(1, 3*mm))

    # TASTE PROFILE
    tp = advanced.get("taste_profile")
    if tp:
        story.append(Paragraph(_c("Your Taste Profile", C_PLUM), sty["SH"]))
        colors = [C_ROSE, C_TEAL, C_INDIGO, C_AMBER, C_SKY, C_CORAL, C_SAGE]
        parts = [_c(tag, colors[i % len(colors)]) for i, tag in enumerate(tp)]
        story.append(Paragraph(" * ".join(parts), sty["BD"]))
        story.append(Spacer(1, 3*mm))

    # RATING BIAS
    rb = advanced.get("rating_bias")
    if rb:
        story.append(Paragraph(_c("Rating Bias", C_AMBER), sty["SH"]))
        rb_data = [
            ["Bias Type", str(rb.get("bias_label", "-")).title()],
            ["Average", "* " + str(rb.get("average", "-"))],
            ["Median", "* " + str(rb.get("median", "-"))],
            ["Mode", "* " + str(rb.get("mode", "-"))],
            ["High Ratings (>=4*)", str(rb.get("high_rating_pct", 0)) + "%"],
            ["Low Ratings (<=2*)", str(rb.get("low_rating_pct", 0)) + "%"],
        ]
        story.append(_tbl(rb_data))
        story.append(Spacer(1, 3*mm))

    # ADVANCED INSIGHTS
    ad = []
    ary = advanced.get("average_release_year")
    if ary:
        ad.append(["Avg Release Year", str(ary)])
    of = advanced.get("oldest_film")
    if of:
        ad.append(["Oldest Film", str(of.get("title", "-")) + " (" + str(of.get("year", "")) + ")"])
    nf = advanced.get("newest_film")
    if nf:
        ad.append(["Newest Film", str(nf.get("title", "-")) + " (" + str(nf.get("year", "")) + ")"])
    mrf = advanced.get("most_rewatched_film")
    if mrf:
        ad.append(["Most Rewatched", str(mrf.get("title", "-")) + " (x" + str(mrf.get("rewatch_count", 0)) + ")"])
    corr = advanced.get("release_year_rating_correlation")
    if corr is not None:
        ad.append(["Year-Rating Correlation", str(corr)])
    ci = advanced.get("correlation_insight")
    if ci:
        ad.append(["Insight", str(ci)])
    if ad:
        story.append(Paragraph(_c("Advanced Insights", C_INDIGO), sty["SH"]))
        story.append(_tbl(ad))
        story.append(Spacer(1, 3*mm))

    # GENRE COMBOS
    gc = advanced.get("most_common_genre_combo")
    if gc:
        story.append(Paragraph(_c("Genre Combos", C_PLUM), sty["SH"]))
        for combo, count in gc[:5]:
            story.append(Paragraph("  * " + _esc(combo) + " - " + _c(str(count) + " films", C_PLUM), sty["SM"]))
        story.append(Spacer(1, 3*mm))

    # YEAR MILESTONES
    hry = pro.get("highest_rated_year")
    lry = pro.get("lowest_rated_year")
    if hry or lry:
        story.append(Paragraph(_c("Year Milestones", C_SKY), sty["SH"]))
        if hry:
            line = "  Best Year: <b>" + str(hry[0]) + "</b> - " + _c("*" + str(hry[1].get("average", "-")), C_SAGE)
            story.append(Paragraph(line, sty["BD"]))
        if lry:
            line = "  Worst Year: <b>" + str(lry[0]) + "</b> - " + _c("*" + str(lry[1].get("average", "-")), C_ROSE)
            story.append(Paragraph(line, sty["BD"]))
        story.append(Spacer(1, 5*mm))

    # FOOTER
    story.append(Spacer(1, 8*mm))
    hr_style = ParagraphStyle("Hr", parent=sty["Normal"], fontSize=6, textColor=TABLE_LINE, alignment=TA_CENTER)
    story.append(Paragraph("--------------------------------------------", hr_style))
    story.append(Spacer(1, 2*mm))
    ft_style = ParagraphStyle("Ft", parent=sty["Normal"], fontSize=9, textColor=TEXT_LIGHT, alignment=TA_CENTER)
    story.append(Paragraph(_c("CineStats", C_INDIGO) + " - Your cinematic journey, visualized.", ft_style))

    doc.build(story)
    buf.seek(0)
    return buf
