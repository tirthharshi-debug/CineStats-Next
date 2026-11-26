import { useMemo, useState } from 'react';
import {
  AlertCircle, ArrowRight, CalendarDays, Clock3, Download,
  Film, LoaderCircle, Share2, Sparkles, Star, Trash2, Upload,
} from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import { deleteJob, describeApiError, downloadReport } from './api';

function Metric({ label, value, note, symbol }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className="metric-symbol">{symbol}</span></div><div className="metric-value">{value ?? '—'}</div>{note ? <div className="metric-note">{note}</div> : null}</div>;
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><span>{label}</span><strong>{payload[0].value}</strong></div>;
}

function AnalyticsSectionHeading({ number, eyebrow, title, note }) {
  return (
    <div className="dash-section-title">
      <div><div className="section-marker"><span>{number}</span><span>{eyebrow}</span></div><h2>{title}</h2></div>
      {note ? <span className="dash-count">{note}</span> : null}
    </div>
  );
}

function DistributionList({ title, data, suffix = '', maxRows = 8 }) {
  const entries = Object.entries(data || {}).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, maxRows);
  if (!entries.length) return null;
  const max = Math.max(1, ...entries.map(item => Number(item[1]) || 0));
  return (
    <article className="data-panel">
      <div className="data-panel-title"><span>{title}</span><span className="eyebrow">{entries.length} SHOWN</span></div>
      <div className="distribution-list">
        {entries.map(([label, value]) => (
          <div className="distribution-row" key={label}>
            <div className="distribution-label"><span title={label}>{label}</span><strong>{value}{suffix}</strong></div>
            <div className="distribution-track"><span style={{ width: ((Number(value) || 0) / max * 100) + '%' }} /></div>
          </div>
        ))}
      </div>
    </article>
  );
}

function RatingList({ title, data }) {
  const entries = Object.entries(data || {}).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, 8);
  if (!entries.length) return null;
  return (
    <article className="data-panel">
      <div className="data-panel-title"><span>{title}</span><span className="eyebrow">AVERAGE RATING</span></div>
      <div className="rating-list">
        {entries.map(([label, value]) => (
          <div className="rating-list-row" key={label}>
            <span>{label}</span><strong><Star size={12} fill="currentColor" /> {Number(value).toFixed(2)}</strong>
          </div>
        ))}
      </div>
    </article>
  );
}

function MiniPoster({ film, size = 'normal' }) {
  const [broken, setBroken] = useState(false);
  const path = film?.poster_path;
  const imageSize = size === 'featured' ? 'w500' : 'w342';
  return (
    <div className={'mini-poster mini-poster-' + size}>
      {path && !broken
        ? <img src={'https://image.tmdb.org/t/p/' + imageSize + path} alt={film?.title || 'Film poster'} loading="lazy" onError={() => setBroken(true)} />
        : <div className="poster-placeholder"><Film size={16} /></div>}
    </div>
  );
}

function FilmComparisonCard({ film, likedMore }) {
  return (
    <article className="comparison-film">
      <MiniPoster film={film} size="comparison" />
      <div className="comparison-film-copy">
        <strong>{film.title}</strong>
        <span>{film.year || 'Release year unknown'}</span>
        <div className="comparison-ratings"><span>You <b>{Number(film.user_rating).toFixed(1)}★</b></span><span>Community <b>{Number(film.tmdb_rating).toFixed(1)}★</b></span></div>
      </div>
      <span className={'comparison-diff ' + (likedMore ? 'diff-up' : 'diff-down')}>{likedMore ? '+' : ''}{Number(film.difference).toFixed(1)}</span>
    </article>
  );
}

function PortraitChip({ name, count, profilePath, extra }) {
  const [broken, setBroken] = useState(false);
  return (
    <article className="portrait-chip">
      <div className="portrait-avatar">
        {profilePath && !broken
          ? <img src={'https://image.tmdb.org/t/p/w185' + profilePath} alt="" loading="lazy" onError={() => setBroken(true)} />
          : <span>{String(name || '?').slice(0, 1).toUpperCase()}</span>}
      </div>
      <div className="portrait-details"><strong title={name}>{name}</strong><span>{count} {count === 1 ? 'film' : 'films'}{extra ? ' · ' + extra : ''}</span></div>
    </article>
  );
}

function ActivityHeatmap({ data }) {
  const { weeks, maxCount, range } = useMemo(() => {
    const entries = Object.entries(data || {}).sort((a, b) => a[0].localeCompare(b[0]));
    if (!entries.length) return { weeks: [], maxCount: 0, range: '' };
    const counts = Object.fromEntries(entries);
    const last = new Date(entries[entries.length - 1][0] + 'T12:00:00');
    const earliest = new Date(entries[0][0] + 'T12:00:00');
    const cutoff = new Date(last); cutoff.setDate(cutoff.getDate() - 364);
    const start = earliest > cutoff ? earliest : cutoff;
    start.setDate(start.getDate() - start.getDay());
    const cursor = new Date(start);
    const result = [];
    const maximum = Math.max(1, ...entries.map(item => Number(item[1]) || 0));
    const keyOf = date => date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    while (cursor <= last) {
      const week = [];
      for (let day = 0; day < 7; day++) {
        const key = keyOf(cursor);
        week.push({ date: key, count: Number(counts[key] || 0) });
        cursor.setDate(cursor.getDate() + 1);
      }
      result.push(week);
      if (result.length > 54) break;
    }
    const fmt = value => value.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    return { weeks: result, maxCount: maximum, range: fmt(start) + ' — ' + fmt(last) };
  }, [data]);
  if (!weeks.length) return <div className="data-empty">A dated diary will turn into a calendar of your screenings.</div>;
  const intensity = count => count === 0 ? 0 : Math.min(4, Math.ceil(count / maxCount * 4));
  return (
    <div className="activity-calendar">
      <div className="activity-calendar-head"><span>{range}</span><span>Days with screenings light up</span></div>
      <div className="heatmap-scroll"><div className="heatmap-grid">
        {weeks.map((week, i) => <div className="heatmap-week" key={i}>
          {week.map(day => <span key={day.date} className={'heatmap-cell heat-' + intensity(day.count)} title={day.date + ': ' + day.count + ' film' + (day.count === 1 ? '' : 's')} />)}
        </div>)}
      </div></div>
      <div className="heatmap-legend"><span>QUIET</span>{[0,1,2,3,4].map(level => <i key={level} className={'heatmap-cell heat-' + level} />)}<span>DOUBLE FEATURE</span></div>
    </div>
  );
}

function RichAnalytics({ patron = {}, advanced = {}, community = {}, binge = {}, monthly = [], decades = [] }) {
  const genres = patron.genre_analytics || {};
  const directors = patron.director_analytics || {};
  const actors = patron.actor_analytics || {};
  const runtime = patron.runtime_analytics || {};
  const countries = patron.country_analytics || {};
  const languages = patron.language_analytics || {};
  const ratedHigher = community.rated_higher || [];
  const ratedLower = community.rated_lower || [];
  const directorsList = Object.entries(directors.director_frequency || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const actorsList = actors.top_10_actors || [];
  const hasWorld = Object.keys(countries.country_distribution || {}).length || Object.keys(languages.language_distribution || {}).length;
  const hasGenres = Object.keys(genres.genre_distribution || {}).length;

  return (
    <div className="rich-analytics">
      <section className="dash-section">
        <AnalyticsSectionHeading number="03" eyebrow="THE SHAPE OF YOUR TASTE" title={<>Your recurring <em>themes.</em></>} note={hasGenres ? Object.keys(genres.genre_distribution).length + ' genres found' : 'Waiting for enriched film data'} />
        {hasGenres ? (
          <div className="rich-grid rich-grid-two">
            <div className="data-panel genre-feature">
              <span className="eyebrow">YOUR SIGNATURE GENRE</span>
              <h3>{genres.most_watched_genre || 'Still taking shape'}</h3>
              <p>Your most frequently watched genre in the rated-film archive. A pattern, not a box to stay inside.</p>
              {genres.favorite_genre?.name ? <div className="favorite-genre"><span>Highest-rated regular genre</span><strong>{genres.favorite_genre.name} <b><Star size={12} fill="currentColor" /> {Number(genres.favorite_genre.avg_rating).toFixed(2)}</b></strong><small>Based on genres with at least five rated films.</small></div> : null}
            </div>
            <DistributionList title="Most watched genres" data={genres.genre_distribution} suffix=" films" maxRows={9} />
            <RatingList title="How you rate each genre" data={genres.average_rating_per_genre} />
            <div className="data-panel">
              <div className="data-panel-title"><span>THE DIRECTOR'S CUT</span><span className="eyebrow">TOP PAIRING</span></div>
              <p className="editorial-note">{advanced.most_common_genre_combo?.length ? 'The most common genre pairing is ' + advanced.most_common_genre_combo[0][0] + ', appearing across ' + advanced.most_common_genre_combo[0][1] + ' enriched titles.' : 'Your film metadata will reveal recurring genre combinations here.'}</p>
              {advanced.taste_profile?.length ? <div className="taste-tags">{advanced.taste_profile.map((tag, i) => <span key={i}>{tag}</span>)}</div> : null}
            </div>
          </div>
        ) : <div className="data-empty">Genre details appear when TMDB can match films in your archive. Your basic diary stats can still be read without a match.</div>}
      </section>

      <section className="dash-section">
        <AnalyticsSectionHeading number="04" eyebrow="THE PEOPLE BEHIND THE FRAME" title={<>Familiar <em>signatures.</em></>} note="Directors & performers" />
        <div className="rich-grid rich-grid-two">
          <div className="data-panel">
            <div className="data-panel-title"><span>DIRECTORS YOU RETURN TO</span><span className="eyebrow">{directorsList.length} SHOWN</span></div>
            {directorsList.length ? <div className="portrait-list">{directorsList.map(([name, count]) => <PortraitChip key={name} name={name} count={count} profilePath={directors.director_profiles?.[name]?.profile_path} extra={directors.director_vs_average?.[name]?.avg ? Number(directors.director_vs_average[name].avg).toFixed(2) + '★ avg' : ''} />)}</div> : <div className="data-empty">Director credits will appear as films are matched.</div>}
          </div>
          <div className="data-panel">
            <div className="data-panel-title"><span>ACTORS IN YOUR ARCHIVE</span><span className="eyebrow">{actorsList.length} SHOWN</span></div>
            {actorsList.length ? <div className="portrait-list">{actorsList.slice(0, 8).map(actor => <PortraitChip key={actor.name} name={actor.name} count={actor.count} profilePath={actor.profile_path} />)}</div> : <div className="data-empty">Cast data will appear as films are matched.</div>}
          </div>
        </div>
      </section>

      <section className="dash-section">
        <AnalyticsSectionHeading number="05" eyebrow="TIME SPENT IN THE DARK" title={<>The hours between <em>credits.</em></>} note="Runtime & activity" />
        <div className="rich-grid rich-grid-two">
          <div className="data-panel runtime-panel">
            <span className="eyebrow">ESTIMATED WATCH TIME</span>
            <div className="runtime-number">{Number(runtime.total_runtime_hours || 0).toLocaleString()}<small> hours</small></div>
            <p>Roughly {Number(runtime.total_runtime_days || 0).toLocaleString()} full days of cinema, based on available runtime metadata for matched films.</p>
            <div className="runtime-facts">
              <div><span>Average feature</span><strong>{runtime.average_runtime ? Math.round(runtime.average_runtime) + ' min' : '—'}</strong></div>
              <div><span>Longest film</span><strong>{runtime.longest_film?.title || '—'}</strong><small>{runtime.longest_film?.runtime ? runtime.longest_film.runtime + ' minutes' : ''}</small></div>
              <div><span>Shortest film</span><strong>{runtime.shortest_film?.title || '—'}</strong><small>{runtime.shortest_film?.runtime ? runtime.shortest_film.runtime + ' minutes' : ''}</small></div>
            </div>
          </div>
          <div className="data-panel">
            <div className="data-panel-title"><span>THE VIEWING CALENDAR</span><span className="eyebrow">DIARY ENTRIES BY DAY</span></div>
            <ActivityHeatmap data={advanced.heatmap_calendar} />
          </div>
        </div>
        {binge.multi_film_days > 0 ? (
          <div className="binge-panel">
            <span className="eyebrow">DOUBLE FEATURES & MARATHONS</span>
            <div className="binge-metrics"><div><strong>{binge.multi_film_days}</strong><span>multi-film days</span></div><div><strong>{binge.max_films_in_day}</strong><span>most films in one day</span></div><div><strong>{binge.avg_films_per_active_day}</strong><span>films per active day</span></div><div><strong>{binge.most_intense_day || '—'}</strong><span>most intense date</span></div></div>
          </div>
        ) : null}
      </section>

      {hasWorld ? <section className="dash-section">
        <AnalyticsSectionHeading number="06" eyebrow="A WORLD OF CINEMA" title={<>Borders are just <em>the frame.</em></>} note="Production & language" />
        <div className="rich-grid rich-grid-two">
          <DistributionList title={'Production countries · lead: ' + (countries.most_watched_country || '—')} data={countries.country_distribution} maxRows={8} />
          <DistributionList title={'Spoken languages · lead: ' + (languages.most_watched_language || '—')} data={languages.language_distribution} maxRows={8} />
        </div>
      </section> : null}

      {monthly.length ? <section className="dash-section">
        <AnalyticsSectionHeading number="07" eyebrow="THE SCREENINGS THAT MADE THE YEARS" title={<>Month by <em>month.</em></>} note={monthly.length + ' months in the diary'} />
        <div className="monthly-shelves">
          {monthly.slice(0, 8).map(month => (
            <article className="monthly-shelf" key={String(month.year) + '-' + month.month}>
              <div className="monthly-shelf-head">
                <div><span className="eyebrow">{month.year}</span><h3>{month.month}</h3></div>
                <div className="monthly-shelf-stats"><strong>{month.total_films}</strong><span>screenings</span><strong>{month.avg_rating ? Number(month.avg_rating).toFixed(1) + '★' : '—'}</strong><span>avg rating</span></div>
              </div>
              <div className="monthly-poster-row">
                {(month.films || []).slice(0, 4).map((film, i) => <div className="monthly-poster" key={film.title + '-' + i} title={film.title}><MiniPoster film={film} size="shelf" /><span>{film.title}</span></div>)}
                {!(month.films || []).length ? <p className="data-empty">No matched posters for this month yet.</p> : null}
                {(month.films || []).length > 4 ? <div className="monthly-more"><span className="monthly-more-count">+{month.films.length - 4}</span><span>more screenings</span><small>Full month in your diary</small></div> : null}
              </div>
            </article>
          ))}
        </div>
      </section> : null}

      {decades.length ? <section className="dash-section">
        <AnalyticsSectionHeading number="08" eyebrow="A WALK THROUGH THE ERAS" title={<>Your golden <em>decades.</em></>} note="Five films or more required" />
        <div className="decade-grid">
          {decades.map((decade, index) => <article className="decade-card" key={decade.decade}>
            <span className="eyebrow">NO. 0{index + 1}</span><h3>{decade.decade}</h3>
            <div className="decade-rating"><Star size={14} fill="currentColor" /> {Number(decade.avg_rating).toFixed(2)}</div>
            <span className="decade-count">{decade.film_count} rated films</span>
            <div className="decade-posters">{(decade.top_posters || []).slice(0, 3).map((film, i) => <MiniPoster film={film} size="decade" key={film.poster_path + '-' + i} />)}</div>
          </article>)}
        </div>
      </section> : null}

      {(ratedHigher.length || ratedLower.length) ? <section className="dash-section">
        <AnalyticsSectionHeading number="09" eyebrow="A PRIVATE CRITICAL VOICE" title={<>You vs <em>the crowd.</em></>} note="Your rating against TMDB community average" />
        <div className="rich-grid rich-grid-two">
          <div className="data-panel">
            <div className="data-panel-title"><span>YOU LOVED IT MORE</span><span className="eyebrow">PERSONAL FAVOURITES</span></div>
            <div className="comparison-stack">{ratedHigher.slice(0, 5).map(film => <FilmComparisonCard key={film.title} film={film} likedMore={true} />)}</div>
            {!ratedHigher.length ? <div className="data-empty">No films in this group yet.</div> : null}
          </div>
          <div className="data-panel">
            <div className="data-panel-title"><span>THE CROWD LOVED IT MORE</span><span className="eyebrow">DIFFERENT TAKES</span></div>
            <div className="comparison-stack">{ratedLower.slice(0, 5).map(film => <FilmComparisonCard key={film.title} film={film} likedMore={false} />)}</div>
            {!ratedLower.length ? <div className="data-empty">No films in this group yet.</div> : null}
          </div>
        </div>
      </section> : null}

      <section className="dash-section">
        <AnalyticsSectionHeading number="10" eyebrow="THE SMALL PRINT OF YOUR TASTE" title={<>What your ratings <em>reveal.</em></>} note="Descriptive, not definitive" />
        {(community.latest_five_star || []).length ? <div className="ratings-film-reel">
          <div className="ratings-film-reel-heading"><span>THE LAST FOUR FILMS YOU LOVED</span><span>YOUR MOST RECENT DISTINCT FIVE-STAR DIARY ENTRIES</span></div>
          <div className="ratings-film-reel-intro"><strong>{community.five_star_count || 0}</strong><span>films in your diary have earned five stars.</span><span className="ratings-film-reel-note">These four are the latest you watched — rewatches don't take extra slots.</span></div>
          <div className="ratings-film-reel-grid">
            {community.latest_five_star.slice(0, 4).map((film, index) => <article className="ratings-film-card" key={(film.title || 'film') + '-' + index}>
              <div className="ratings-film-poster"><MiniPoster film={film} size="featured" /><span className="ratings-film-index">0{index + 1}</span><span className="ratings-film-score">5.0 <i>★</i></span></div>
              <div className="ratings-film-copy"><h3>{film.title || 'Untitled film'}</h3><span>{film.year || 'Year unknown'}</span><span className="ratings-film-watched">{film.watched_date ? 'WATCHED ' + film.watched_date : 'FIVE-STAR FILM'}</span></div>
            </article>)}
          </div>
        </div> : <div className="ratings-film-reel ratings-film-reel-empty"><div className="ratings-film-reel-heading"><span>YOUR FIVE-STAR CLUB</span></div><p>No matched five-star diary films were found yet. Rate films five stars and add them to your diary to build this reel.</p></div>}
        <div className="rich-grid rich-grid-two">
          <div className="data-panel">
            <div className="data-panel-title"><span>YOUR RATING TEMPERAMENT</span><span className="eyebrow">SELF-REPORTED RATINGS</span></div>
            {advanced.rating_bias ? <>
              <div className="bias-heading"><span className="bias-label">{advanced.rating_bias.bias_label} rater</span><span className="eyebrow">THE PATTERN, NOT A JUDGEMENT</span></div>
              <div className="rating-bias-grid">
                <div><strong>{Number(advanced.rating_bias.average).toFixed(2)}</strong><span>mean</span></div>
                <div><strong>{Number(advanced.rating_bias.median).toFixed(2)}</strong><span>median</span></div>
                <div><strong>{Number(advanced.rating_bias.mode).toFixed(2)}</strong><span>mode</span></div>
              </div>
              <div className="bias-bars"><div><span>4★ or higher</span><strong>{advanced.rating_bias.high_rating_pct}%</strong><i><b style={{ width: advanced.rating_bias.high_rating_pct + '%' }} /></i></div><div><span>2★ or lower</span><strong>{advanced.rating_bias.low_rating_pct}%</strong><i><b style={{ width: advanced.rating_bias.low_rating_pct + '%' }} /></i></div></div>
            </> : <div className="data-empty">Rate films to uncover your personal rating pattern.</div>}
          </div>
          <div className="data-panel">
            <div className="data-panel-title"><span>THE YEARS ON THE TICKET</span><span className="eyebrow">RELEASE-YEAR REFLECTION</span></div>
            <div className="release-pair">
              <div className="release-stat-average"><span>Average release year</span><strong>{advanced.average_release_year || '—'}</strong></div>
              <div className="release-stat-film"><span className="release-stat-label">Oldest matched film</span><div className="release-stat-content">{advanced.oldest_film?.poster_path ? <MiniPoster film={advanced.oldest_film} size="shelf" /> : null}<div><strong>{advanced.oldest_film?.title || '—'}</strong><small>{advanced.oldest_film?.year || ''}</small></div></div></div>
              <div className="release-stat-film"><span className="release-stat-label">Newest matched film</span><div className="release-stat-content">{advanced.newest_film?.poster_path ? <MiniPoster film={advanced.newest_film} size="shelf" /> : null}<div><strong>{advanced.newest_film?.title || '—'}</strong><small>{advanced.newest_film?.year || ''}</small></div></div></div>
              <div className="release-stat-film"><span className="release-stat-label">Most rewatched</span><div className="release-stat-content">{advanced.most_rewatched_film?.poster_path ? <MiniPoster film={advanced.most_rewatched_film} size="shelf" /> : null}<div><strong>{advanced.most_rewatched_film?.title || '—'}</strong><small>{advanced.most_rewatched_film ? advanced.most_rewatched_film.rewatch_count + ' rewatch entries' : ''}</small></div></div></div>
            </div>
            {advanced.correlation_insight ? <p className="editorial-note">{advanced.correlation_insight} <span className="correlation-stat">Correlation: {advanced.release_year_rating_correlation ?? 'not enough data'}</span></p> : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function EmptyChart({ note }) {
  return <div className="empty-chart"><div className="empty-chart-icon"><Film size={22} /></div><p>{note}</p></div>;
}

export default function AnalyticsDashboard({ data, jobId, jobToken, onImport, onHome }) {
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [sharingTopFour, setSharingTopFour] = useState(false);
  const [shareError, setShareError] = useState('');
  const { stats = {}, meta = {} } = data || {};
  const basic = stats.basic || {};
  const pro = stats.pro || {};
  const patron = stats.patron || {};
  const yearData = useMemo(() => Object.entries(basic.films_per_year || {}).map(([year, count]) => ({ year, count })).sort((a, b) => Number(a.year) - Number(b.year)), [basic.films_per_year]);
  const ratingData = useMemo(() => Object.entries(basic.rating_distribution || {}).map(([rating, count]) => ({ rating: rating + '★', count })), [basic.rating_distribution]);
  const handlePdf = async () => {
    setDownloading(true); setDownloadError('');
    try {
      const blob = await downloadReport(jobId, jobToken);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'CineStats-Your-Film-Life.pdf';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setDownloadError(describeApiError(err, 'The report could not be generated. Please try again.'));
    } finally { setDownloading(false); }
  };

  const handleDelete = async () => {
    if (!jobId || !jobToken || deleting) return;
    setDeleting(true);
    setDownloadError('');
    try {
      await deleteJob(jobId, jobToken);
      onHome();
    } catch (err) {
      setDownloadError(describeApiError(err, 'Your data could not be deleted. Please try again.'));
    } finally {
      setDeleting(false);
    }
  };

  const handleShareTopFour = async () => {
    const favourites = (stats.favorite_films || []).slice(0, 4);
    if (!favourites.length || sharingTopFour) return;
    setSharingTopFour(true);
    setShareError('');
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 1200;
      canvas.height = 1850;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Your browser could not prepare the share card.');
      context.fillStyle = '#141311';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.strokeStyle = 'rgba(213,171,106,0.38)';
      context.lineWidth = 2;
      context.strokeRect(38, 38, canvas.width - 76, canvas.height - 76);
      context.fillStyle = '#d5ab6a';
      context.font = '600 18px monospace';
      context.letterSpacing = '4px';
      context.fillText('CINESTATS  /  PERSONAL CINEMATHEQUE', 76, 102);
      context.fillStyle = '#eee7d9';
      context.font = '500 66px Georgia, serif';
      context.letterSpacing = '0px';
      context.fillText('Four that stay', 76, 190);
      context.fillStyle = '#d94c3a';
      context.font = 'italic 66px Georgia, serif';
      context.fillText('with you.', 76, 264);

      const gap = 24;
      const left = 76;
      const top = 326;
      const posterWidth = 500;
      const posterHeight = 630;
      const posterImages = await Promise.all(favourites.map(film => new Promise(resolve => {
        if (!film?.poster_path) return resolve(null);
        const image = new Image();
        image.crossOrigin = 'anonymous';
        image.onload = () => resolve(image);
        image.onerror = () => resolve(null);
        image.src = 'https://image.tmdb.org/t/p/w500' + film.poster_path;
      })));

      favourites.forEach((film, index) => {
        const col = index % 2;
        const row = Math.floor(index / 2);
        const x = left + col * (posterWidth + gap);
        const y = top + row * (posterHeight + 66);
        context.fillStyle = '#201e1a';
        context.fillRect(x, y, posterWidth, posterHeight);
        const image = posterImages[index];
        if (image) {
          const scale = Math.max(posterWidth / image.width, posterHeight / image.height);
          const sw = posterWidth / scale;
          const sh = posterHeight / scale;
          context.drawImage(image, (image.width - sw) / 2, (image.height - sh) / 2, sw, sh, x, y, posterWidth, posterHeight);
        } else {
          context.strokeStyle = 'rgba(213,171,106,0.4)';
          context.strokeRect(x + 18, y + 18, posterWidth - 36, posterHeight - 36);
          context.fillStyle = '#d5ab6a';
          context.font = '20px monospace';
          context.fillText('0' + (index + 1) + ' / FAVOURITE', x + 34, y + 58);
          context.fillStyle = '#eee7d9';
          context.font = '42px Georgia, serif';
          const words = String(film?.title || 'Film details unavailable').split(' ');
          let line = '';
          let lineY = y + 340;
          words.forEach(word => {
            const test = line ? line + ' ' + word : word;
            if (context.measureText(test).width > posterWidth - 68 && line) {
              context.fillText(line, x + 34, lineY);
              line = word;
              lineY += 52;
            } else line = test;
          });
          if (line) context.fillText(line, x + 34, lineY);
        }
        context.fillStyle = '#eee7d9';
        context.font = '600 24px Georgia, serif';
        const title = String(film?.title || 'Favourite film');
        context.fillText(title.length > 34 ? title.slice(0, 31) + '…' : title, x, y + posterHeight + 35);
        context.fillStyle = '#9e988b';
        context.font = '16px monospace';
        context.fillText(String(film?.year || 'YEAR UNKNOWN'), x, y + posterHeight + 59);
      });

      context.strokeStyle = 'rgba(213,171,106,0.25)';
      context.beginPath();
      context.moveTo(76, 1770);
      context.lineTo(1124, 1770);
      context.stroke();
      context.fillStyle = '#9e988b';
      context.font = '16px monospace';
      context.fillText('YOUR LETTERBOXD PROFILE FAVOURITES  ·  IN YOUR ORIGINAL ORDER', 76, 1805);

      const blob = await new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('The share card could not be exported.')), 'image/png'));
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'CineStats-Top-Four.png';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(url), 1500);
    } catch (error) {
      setShareError(error?.message || 'The share card could not be created. Please try again.');
    } finally {
      setSharingTopFour(false);
    }
  };

  return (
    <main className="dashboard section-shell">
      <div className="dashboard-masthead"><div><div className="eyebrow"><span className="eyebrow-line" /> YOUR CINEMATHEQUE / PRIVATE EDITION</div><h1>The story so<br /><em>far.</em></h1><p className="dashboard-intro">A personal film journal, assembled from the films you've lived with. Your history, your patterns, your own point of view.</p></div><div className="dashboard-actions"><button className="button button-outline" onClick={onImport}><Upload size={15} /> Add an export</button><button className="button button-outline" onClick={handleDelete} disabled={deleting || !jobId || !jobToken}>{deleting ? <LoaderCircle size={15} className="spin" /> : <Trash2 size={15} />}{deleting ? 'Deleting…' : 'Delete my data'}</button><button className="button button-primary" onClick={handlePdf} disabled={downloading}>{downloading ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}{downloading ? 'Preparing…' : 'Print my archive'}</button></div></div>
      {downloadError ? <p className="form-error dashboard-error"><AlertCircle size={15} /> {downloadError}</p> : null}
      <div className="dashboard-rule"><span>THE JOURNAL AT A GLANCE</span><span>NOTHING HERE IS GUESSED</span></div>
      <div className="metric-grid">
        <Metric label="Films in your archive" value={Number(basic.total_films || 0).toLocaleString()} note="Unique films watched" symbol={<Film size={15} />} />
        <Metric label="Screenings logged" value={Number(basic.total_diary_entries || 0).toLocaleString()} note="Diary entries, rewatches included" symbol={<CalendarDays size={15} />} />
        <Metric label="Your average rating" value={basic.average_rating ? Number(basic.average_rating).toFixed(2) + ' ★' : '—'} note="From your ratings" symbol={<Star size={15} />} />
        <Metric label="Longest streak" value={Number(pro.longest_watch_streak || 0) + ' days'} note="Consecutive days with a diary entry" symbol={<Clock3 size={15} />} />
      </div>
      {(stats.favorite_films || []).length ? <section className="top-four-section">
        <div className="top-four-heading">
          <div><div className="section-marker"><span>00</span><span>YOUR LETTERBOXD PROFILE FAVOURITES</span></div><h2>Four that <em>stay with you.</em></h2><p>The four films you chose for your profile, in your original order. Your taste, your call.</p></div>
          <div className="top-four-heading-actions">
            <span className="top-four-note">YOUR PERSONAL CANON · FOUR FRAMES, FOREVER</span>
            <button className="button button-outline top-four-share" type="button" onClick={handleShareTopFour} disabled={sharingTopFour} aria-label="Download a shareable image of your Letterboxd Top Four">
              {sharingTopFour ? <LoaderCircle size={15} className="spin" /> : <Share2 size={15} />}
              {sharingTopFour ? 'Making card…' : 'Share my four'}
            </button>
          </div>
        </div>
        {shareError ? <p className="form-error top-four-share-error" role="status">{shareError}</p> : null}
        <div className="top-four-grid">
          {stats.favorite_films.slice(0, 4).map((film, index) => <article className="top-four-card" key={film.favorite_url || (film.title + '-' + index)}>
            <div className="top-four-art"><MiniPoster film={film} size="featured" /><span className="top-four-index">0{index + 1}</span><span className="top-four-rating">{film.resolved ? 'IN YOUR CANON' : 'UNRESOLVED'}</span><span className="top-four-frame-mark" aria-hidden="true">✳</span></div>
            <div className="top-four-copy"><span className="top-four-position">FRAME 0{index + 1}</span><h3>{film.title || 'Favourite film'}</h3><span>{film.year || (film.resolved ? 'Release year unknown' : 'Film details unavailable')}</span></div>
          </article>)}
        </div>
        <div className="top-four-footerline"><span>FOUR FILMS. A THOUSAND FEELINGS.</span><span>SELECTED BY YOU · NEVER RANKED BY AN ALGORITHM</span></div>
      </section> : null}
      <section className="dash-section">
        <div className="dash-section-title"><div><div className="section-marker"><span>01</span><span>THE PASSAGE OF TIME</span></div><h2>Your years <em>in film.</em></h2></div><span className="dash-count">{yearData.length} {yearData.length === 1 ? 'year' : 'years'} represented</span></div>
        <div className="chart-grid">
          <article className="chart-panel chart-wide"><div className="chart-panel-heading"><div><span className="eyebrow">WATCHING HISTORY</span><h3>The years you showed up</h3></div><span className="chart-ornament">01—∞</span></div>{yearData.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><BarChart data={yearData} margin={{ top: 12, right: 8, left: -20, bottom: 0 }}><CartesianGrid vertical={false} stroke="rgba(238,231,217,.1)" /><XAxis dataKey="year" tick={{ fill: '#9e988b', fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: '#9e988b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} /><Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(220,75,58,.07)' }} /><Bar dataKey="count" name="Films" fill="#d94c3a" radius={[3, 3, 0, 0]} maxBarSize={42} /></BarChart></ResponsiveContainer></div> : <EmptyChart note="Your diary entries will bring this timeline to life." />}</article>
          <article className="chart-panel"><div className="chart-panel-heading"><div><span className="eyebrow">THE STAR SYSTEM</span><h3>Your ratings, in full</h3></div><Star size={17} /></div>{ratingData.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><LineChart data={ratingData} margin={{ top: 16, right: 8, left: -20, bottom: 0 }}><CartesianGrid vertical={false} stroke="rgba(238,231,217,.1)" /><XAxis dataKey="rating" tick={{ fill: '#9e988b', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: '#9e988b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} /><Tooltip content={<ChartTooltip />} /><Line dataKey="count" stroke="#d5ab6a" strokeWidth={2} dot={{ r: 3, fill: '#d5ab6a', strokeWidth: 0 }} activeDot={{ r: 5 }} /></LineChart></ResponsiveContainer></div> : <EmptyChart note="Rate films in Letterboxd to reveal your rating curve." />}</article>
        </div>
      </section>
      <section className="dash-section">
        <div className="dash-section-title"><div><div className="section-marker"><span>02</span><span>THE HUMAN SIDE OF CINEMA</span></div><h2>Patterns worth <em>noticing.</em></h2></div></div>
        <div className="insight-grid">
          <article className="insight-note"><span className="insight-number">A</span><span className="eyebrow">YOUR FIRST FRAME</span><h3>{basic.first_watched?.title || 'The beginning'}</h3><p>{basic.first_watched?.date ? 'The earliest dated film in your diary, on ' + basic.first_watched.date + '.' : 'Add dated entries to find the opening chapter of your film diary.'}</p></article>
          <article className="insight-note"><span className="insight-number">B</span><span className="eyebrow">UNTIL NEXT TIME</span><h3>{basic.most_recent_watched?.title || 'The latest chapter'}</h3><p>{basic.most_recent_watched?.date ? 'Your most recent dated entry, on ' + basic.most_recent_watched.date + '.' : 'Your latest dated diary entry will appear here.'}</p></article>
          <article className="insight-note"><span className="insight-number">C</span><span className="eyebrow">THE RETURNING VIEWER</span><h3>{Number(basic.total_rewatches || 0).toLocaleString()} rewatches</h3><p>Some films get better with time. These are the return visits recorded in your diary.</p></article>
        </div>
      </section>

      <RichAnalytics patron={patron} advanced={stats.advanced || {}} community={stats.community_comparison || {}} binge={stats.binge_stats || {}} monthly={stats.monthly_activity || []} decades={stats.decade_leaderboard || []} />
      <section className="dash-footer-note"><Sparkles size={17} /><p><strong>This is a record, not a verdict.</strong> Stats reflect what's present in your export. The most important part of your film life may never fit inside a chart.</p></section>
      <button className="back-link" onClick={onHome}><ArrowRight size={15} /> Back to the opening credits</button>
      <div className="dashboard-meta"><span>{meta.total_unique_movies || basic.total_films || 0} unique titles discovered</span><span>YOUR PERSONAL CINEMATHEQUE · CS/NEXT</span></div>
    </main>
  );
}
