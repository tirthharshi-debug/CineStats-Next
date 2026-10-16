import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays,
  CheckCircle2, ChevronDown, ChevronRight, CirclePlay, Clapperboard,
  Clock3, Download, Film, Github, Heart, LoaderCircle, Menu, Search,
  Sparkles, Star, Ticket, Upload, X,
} from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import { downloadReport, getJobProgress, getJobResults, uploadLetterboxdExport } from './api';

const ease = [0.22, 1, 0.36, 1];
function LetterboxdMark({ size = 22 }) {
  const id = useId().replace(/:/g, '-');
  const clip1Id = `lb-clip-1-${id}`;
  const clip2Id = `lb-clip-2-${id}`;
  return (
    <svg viewBox="0 0 84 36" width={Math.round(size * 84 / 36)} height={size} fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <clipPath id={clip1Id}><circle cx="18" cy="18" r="16" /></clipPath>
        <clipPath id={clip2Id}><circle cx="42" cy="18" r="16" /></clipPath>
      </defs>
      <circle cx="18" cy="18" r="16" fill="#ff8000" />
      <circle cx="42" cy="18" r="16" fill="#00e054" />
      <circle cx="66" cy="18" r="16" fill="#40bcf4" />
      <circle cx="42" cy="18" r="16" fill="#ffffff" clipPath={`url(#${clip1Id})`} />
      <circle cx="66" cy="18" r="16" fill="#ffffff" clipPath={`url(#${clip2Id})`} />
    </svg>
  );
}

function Brand({ onClick }) {
  return (
    <button className="brand" onClick={onClick} aria-label="CineStats home">
      <img className="brand-logo-image" src="/images/cinestats-logo.webp" alt="CineStats" />
    </button>
  );
}

function Header({ onImport, onHome, dashboard = false }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Brand onClick={onHome} />
        <nav className={'main-nav ' + (menuOpen ? 'main-nav-open' : '')} aria-label="Main navigation">
          <a href="#manifesto" onClick={() => setMenuOpen(false)}>The idea</a>
          <a href="#archive" onClick={() => setMenuOpen(false)}>The archive</a>
          <a href="#about" onClick={() => setMenuOpen(false)}>About</a>
        </nav>
        <div className="topbar-actions">
          <a className="letterboxd-profile-link" href="https://boxd.it/8hpsV" target="_blank" rel="noopener noreferrer" aria-label="Letterboxd profile"><LetterboxdMark size={24} /></a>
          <span className="edition-note"><span className="live-dot" /> MADE FOR FILM LOVERS</span>
          <button className="button button-small button-dark" onClick={onImport}>
            {dashboard ? 'Import another' : 'Open your archive'} <ArrowUpRight size={15} />
          </button>
          <button className="icon-button mobile-menu" aria-label="Toggle menu" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>
    </header>
  );
}

function UploadModal({ onClose, onComplete }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobProgress, setJobProgress] = useState({ status: 'idle', current: 0, total: 0 });
  const [messageIndex, setMessageIndex] = useState(0);
  const [error, setError] = useState('');
  const inputRef = useRef(null);
  const cancelled = useRef(false);

  useEffect(() => () => { cancelled.current = true; }, []);

  const working = phase === 'uploading' || phase === 'processing';
  useEffect(() => {
    if (!working) { setMessageIndex(0); return undefined; }
    const interval = window.setInterval(() => setMessageIndex(index => (index + 1) % 6), 5200);
    return () => window.clearInterval(interval);
  }, [working]);

  const acceptFile = (candidate) => {
    setError('');
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith('.zip')) {
      setError('Please choose the original .zip export from Letterboxd.');
      return;
    }
    if (candidate.size > 10 * 1024 * 1024) {
      setError('This file is over 10 MB. The current API accepts exports up to 10 MB.');
      return;
    }
    setFile(candidate);
  };

  const processFile = async () => {
    if (!file || phase === 'uploading' || phase === 'processing') return;
    cancelled.current = false;
    setError('');
    setPhase('uploading');
    setUploadProgress(0);
    try {
      const started = await uploadLetterboxdExport(file, setUploadProgress);
      if (!started?.job_id) throw new Error('The analysis service did not return a job ID.');
      setPhase('processing');
      let attempts = 0;
      while (!cancelled.current && attempts < 900) {
        attempts += 1;
        const progress = await getJobProgress(started.job_id);
        setJobProgress(progress);
        if (progress.status === 'error') throw new Error(progress.error || 'The analysis could not be completed.');
        if (progress.status === 'done') {
          const result = await getJobResults(started.job_id);
          if (!result?.stats) throw new Error('The API returned no analytics data.');
          onComplete(result, started.job_id);
          return;
        }
        await new Promise(resolve => window.setTimeout(resolve, 1300));
      }
      if (!cancelled.current) throw new Error('This analysis is taking longer than expected. Please try again.');
    } catch (err) {
      if (!cancelled.current) {
        const detail = err?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : (err.message || 'Something went wrong while reading your archive.'));
        setPhase('idle');
      }
    }
  };

  const movieCount = jobProgress.total > 0 ? Math.min(100, Math.round((jobProgress.current / jobProgress.total) * 100)) : 0;
  const intermissionMessages = [
    { title: 'Every diary has an opening scene.', note: 'Preparing the frames that make up your film life.' },
    { title: 'Finding the films you return to.', note: 'Reading your watch history and recorded rewatches.' },
    { title: 'Looking for familiar names.', note: 'Matching titles and filmmakers where data is available.' },
    { title: 'Following the thread through the years.', note: 'Organising your actual diary entries into a timeline.' },
    { title: 'Making room for the unexpected.', note: 'Your patterns are emerging from the archive.' },
    { title: 'A little patience between the frames.', note: 'Larger archives can take a little longer to read.' },
  ];
  const intermission = intermissionMessages[messageIndex];

  return (
    <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={event => { if (event.target === event.currentTarget && !working) onClose(); }}>
      <motion.section className="import-modal" role="dialog" aria-modal="true" aria-labelledby="import-title" initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12 }} transition={{ duration: 0.32, ease }}>
        <div className="modal-topline"><span className="eyebrow"><Ticket size={13} /> YOUR PERSONAL ARCHIVE</span><button className="icon-button" onClick={onClose} disabled={working} aria-label="Close import dialog"><X size={18} /></button></div>
        <h2 id="import-title">Every film has a <em>place.</em></h2>
        <p className="modal-intro">Bring your Letterboxd diary home. Your export is read to build a portrait of the way you watch.</p>
        {!working ? (
          <>
            <div className={'upload-drop ' + (dragging ? 'upload-drop-active' : '') + (file ? ' upload-drop-ready' : '')}
              onDragOver={event => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={event => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files?.[0]); }}>
              <input ref={inputRef} type="file" accept=".zip,application/zip" hidden onChange={event => acceptFile(event.target.files?.[0])} />
              <div className="upload-icon"><Upload size={22} strokeWidth={1.5} /></div>
              {file ? (
                <><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · Ready for the first screening</span>
                  <button className="text-button" onClick={() => { setFile(null); if (inputRef.current) inputRef.current.value = ''; }}>Choose a different file</button></>
              ) : (
                <><strong>Drop your Letterboxd export here</strong><span>ZIP archive · up to 10 MB</span><button className="button button-outline" onClick={() => inputRef.current?.click()}>Choose a file <ArrowRight size={15} /></button></>
              )}
            </div>
            {error ? <p className="form-error"><AlertCircle size={15} /> {error}</p> : null}
            <div className="import-steps"><div><span>01</span><p>Export your data at <a href="https://letterboxd.com/data/export/" target="_blank" rel="noreferrer">Letterboxd ↗</a></p></div><div><span>02</span><p>Upload the original ZIP</p></div><div><span>03</span><p>Explore your film life</p></div></div>
            <button className="button button-primary button-wide" disabled={!file} onClick={processFile}>Read my film diary <ArrowRight size={17} /></button>
            <p className="privacy-note">Your export is processed by the configured CineStats API. Don't upload anything you don't want processed.</p>
          </>
        ) : (
          <div className="processing-panel processing-cinema">
            <div className="intermission-art" aria-hidden="true">
              <span className="projector-beam" />
              <div className="film-strip film-strip-upper">
                <div className="film-strip-track">
                  {Array.from({ length: 2 }).map((_, reel) => <div className="film-strip-run" key={reel}>
                    {['01', '02', '03', '04', '05', '06'].map(frame => <span className="film-cell" key={frame}><i>{frame}</i><b /><small>CS / 35</small></span>)}
                  </div>)}
                </div>
              </div>
              <div className="film-strip film-strip-lower">
                <div className="film-strip-track">
                  {Array.from({ length: 2 }).map((_, reel) => <div className="film-strip-run" key={reel}>
                    {['07', '08', '09', '10', '11', '12'].map(frame => <span className="film-cell" key={frame}><i>{frame}</i><b /><small>CS / 35</small></span>)}
                  </div>)}
                </div>
              </div>
              <span className="projector-glint" />
              <div className="intermission-caption">A PERSONAL CINEMATHEQUE <span>·</span> FRAMES IN MOTION</div>
            </div>
            <span className="eyebrow"><span className="live-dot" /> {phase === 'uploading' ? 'THE REEL IS ARRIVING' : jobProgress.status === 'enriching' ? 'IN THE CUTTING ROOM' : 'READING YOUR FILM DIARY'}</span>
            <h3 key={phase === 'uploading' ? 'uploading' : messageIndex} className="intermission-title">{phase === 'uploading' ? 'Getting your archive on screen.' : intermission.title}</h3>
            <p className="intermission-note">{phase === 'uploading' ? 'Sending your Letterboxd export to the analysis service.' : intermission.note}</p>
            <div className="intermission-stage"><span className={phase === 'uploading' ? 'stage-active' : 'stage-done'}>01 <i>THE EXPORT</i></span><span className={phase === 'processing' ? 'stage-active' : ''}>02 <i>THE ARCHIVE</i></span><span>03 <i>THE REVEAL</i></span></div>
            <div className="progress-track"><span style={{ width: (phase === 'uploading' ? uploadProgress : movieCount) + '%' }} /></div>
            <div className="progress-label"><span>{phase === 'uploading' ? uploadProgress + '% uploaded' : (jobProgress.current + ' / ' + jobProgress.total + ' titles enriched')}</span><span>{phase === 'processing' && movieCount ? movieCount + '%' : ''}</span></div>
            {error ? <p className="form-error"><AlertCircle size={15} /> {error}</p> : null}
            <button className="text-button" onClick={() => { cancelled.current = true; setPhase('idle'); setError('Processing stopped in this window. The server job may continue until it expires.'); }}>Stop waiting <ArrowRight size={14} /></button>
          </div>
        )}
      </motion.section>
    </motion.div>
  );
}

function LandingPage({ onImport }) {
  return (
    <>
      <section className="hero section-shell">
        <div className="hero-copy">
          <div className="eyebrow hero-eyebrow"><span className="eyebrow-line" /> A HOME FOR YOUR FILM LIFE <span className="edition-number">VOL. 01 — 2026</span></div>
          <h1>A life<br />in <em>film.</em></h1>
          <p className="hero-deck">Not another list of things you've watched. A living portrait of the films that found you, changed you, and stayed long after the credits.</p>
          <div className="hero-actions"><button className="button button-primary" onClick={onImport}>Enter your cinematheque <ArrowUpRight size={17} /></button><a className="quiet-link" href="#manifesto">Get the idea <ArrowDownRight size={15} /></a></div>
          <div className="hero-footnote"><span className="mini-star">✳</span><span>Made for people who stay until the last frame.</span></div>
        </div>
        <div className="hero-visual" aria-label="Abstract cinematic poster artwork">
          <div className="hero-orbit orbit-a" /><div className="hero-orbit orbit-b" />
          <div className="hero-film-still">
            <div className="still-frame-label"><span>CS / 001</span><span>A STUDY IN LIGHT</span></div>
            <div className="still-sun" /><div className="still-horizon" /><div className="still-shadow" />
            <div className="still-title"><span>THE ART OF</span><strong>LOOKING</strong><em>closer.</em></div>
            <div className="still-credit">A PERSONAL CINEMATHEQUE<br />FOR THE YEARS AHEAD</div>
            <span className="frame-corner frame-corner-tl" /><span className="frame-corner frame-corner-br" />
          </div>
          <div className="visual-side-note">A PRIVATE ARCHIVE / A PUBLIC LOVE LETTER</div>
          <div className="visual-index">35<span>MM</span></div>
        </div>
      </section>

      <div className="ticker" aria-label="CineStats principles"><div className="ticker-track">
        {Array.from({ length: 2 }).map((_, set) => <span className="ticker-set" key={set}>
          <span>THE DIRECTOR'S CUT</span><i>✳</i><span>YOUR TASTE, IN FOCUS</span><i>✳</i><span>EVERY FRAME COUNTS</span><i>✳</i><span>THE SHOW GOES ON</span><i>✳</i>
        </span>)}
      </div></div>

      <section className="manifesto section-shell" id="manifesto">
        <div className="section-marker"><span>01</span><span>THE REASON WE'RE HERE</span></div>
        <div className="manifesto-grid">
          <h2>Some films are<br />watched. Others<br /><em>become part of you.</em></h2>
          <div className="manifesto-body"><span className="large-quote">“</span><p>Your film diary already holds a story. The first five-star film. The director you keep returning to. The year you couldn't stop going to the cinema. We give those details the space they deserve.</p><p className="manifesto-signature">A LITTLE MORE MEANING BETWEEN THE FRAMES.</p></div>
        </div>
      </section>

      <section className="archive-section archive-manifesto" id="archive">
        <div className="section-shell archive-manifesto-inner">
          <div className="archive-manifesto-art">
            <img
              className="archive-theatre-image"
              src="/images/archive-theatre.webp"
              alt="An intimate boutique cinema with burgundy seats and a ceiling-mounted projector illuminating the screen."
              loading="lazy"
              decoding="async"
            />
            <span className="archive-frame-number">CS / 002</span>
            <span className="archive-frame-caption">NO BORROWED TASTE</span>
          </div>
          <div className="archive-manifesto-copy">
            <div className="section-marker"><span>02</span><span>NO CANON. NO CHECKLIST.</span></div>
            <h2>Your taste.<br /><em>Your own cut.</em></h2>
            <p>We won't tell you what a cinephile should watch. No borrowed favourites, no prescribed canon. Bring your own diary, and let the films you've actually lived with tell the story.</p>
            <div className="archive-bottom"><span><span className="small-dot" /> BUILT FROM YOUR LETTERBOXD EXPORT</span><button className="text-button" onClick={onImport}>Read my film diary <ArrowRight size={15} /></button></div>
          </div>
        </div>
      </section>

      <section className="features-section section-shell">
        <div className="section-marker"><span>03</span><span>BEYOND THE COUNT</span></div>
        <div className="feature-heading"><h2>Numbers with<br /><em>a point of view.</em></h2><p>Analytics should help you see your own taste with fresh eyes. Not turn your love of cinema into a competition.</p></div>
        <div className="feature-list">
          <article className="feature-row"><span className="feature-index">A / 01</span><div className="feature-symbol"><CalendarDays size={21} /></div><div className="feature-copy"><h3>The rhythm of your watching</h3><p>Seasons, streaks, double features, the quiet months and the years you couldn't get enough.</p></div><ArrowUpRight className="feature-arrow" size={19} /></article>
          <article className="feature-row"><span className="feature-index">B / 02</span><div className="feature-symbol"><Star size={21} /></div><div className="feature-copy"><h3>The shape of your taste</h3><p>Ratings, favourite genres, directors you trust, and the gap between a film's reputation and your own feeling.</p></div><ArrowUpRight className="feature-arrow" size={19} /></article>
          <article className="feature-row"><span className="feature-index">C / 03</span><div className="feature-symbol"><Heart size={21} /></div><div className="feature-copy"><h3>The films that find you again</h3><p>Rewatches, recurring obsessions, and the filmmakers who keep earning a place in your life.</p></div><ArrowUpRight className="feature-arrow" size={19} /></article>
        </div>
        <div className="feature-cta"><div><span className="eyebrow">THE NEXT SCREENING IS YOURS</span><h3>Let's see what your<br /><em>film life looks like.</em></h3></div><button className="button button-primary" onClick={onImport}>Open your archive <ArrowUpRight size={17} /></button></div>
      </section>
    </>
  );
}

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
                {(month.films || []).slice(0, 10).map((film, i) => <div className="monthly-poster" key={film.title + '-' + i} title={film.title}><MiniPoster film={film} size="shelf" /><span>{film.title}</span></div>)}
                {!(month.films || []).length ? <p className="data-empty">No matched posters for this month yet.</p> : null}
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
            <div className="release-pair"><div><span>Average release year</span><strong>{advanced.average_release_year || '—'}</strong></div><div><span>Oldest matched film</span><strong>{advanced.oldest_film?.title || '—'}</strong><small>{advanced.oldest_film?.year || ''}</small></div><div><span>Newest matched film</span><strong>{advanced.newest_film?.title || '—'}</strong><small>{advanced.newest_film?.year || ''}</small></div><div><span>Most rewatched</span><strong>{advanced.most_rewatched_film?.title || '—'}</strong><small>{advanced.most_rewatched_film ? advanced.most_rewatched_film.rewatch_count + ' rewatch entries' : ''}</small></div></div>
            {advanced.correlation_insight ? <p className="editorial-note">{advanced.correlation_insight} <span className="correlation-stat">Correlation: {advanced.release_year_rating_correlation ?? 'not enough data'}</span></p> : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function AnalyticsDashboard({ data, jobId, onImport, onHome }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const { stats = {}, meta = {} } = data || {};
  const basic = stats.basic || {};
  const pro = stats.pro || {};
  const patron = stats.patron || {};
  const yearData = useMemo(() => Object.entries(basic.films_per_year || {}).map(([year, count]) => ({ year, count })).sort((a, b) => Number(a.year) - Number(b.year)), [basic.films_per_year]);
  const ratingData = useMemo(() => Object.entries(basic.rating_distribution || {}).map(([rating, count]) => ({ rating: rating + '★', count })), [basic.rating_distribution]);
  const handlePdf = async () => {
    setDownloading(true); setDownloadError('');
    try {
      const blob = await downloadReport(jobId);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'CineStats-Your-Film-Life.pdf'; anchor.click();
      window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setDownloadError(err?.response?.data?.detail || 'The report could not be generated. Please try again.');
    } finally { setDownloading(false); }
  };
  return (
    <main className="dashboard section-shell">
      <div className="dashboard-masthead"><div><div className="eyebrow"><span className="eyebrow-line" /> YOUR CINEMATHEQUE / PRIVATE EDITION</div><h1>The story so<br /><em>far.</em></h1><p className="dashboard-intro">A personal film journal, assembled from the films you've lived with. Your history, your patterns, your own point of view.</p></div><div className="dashboard-actions"><button className="button button-outline" onClick={onImport}><Upload size={15} /> Add an export</button><button className="button button-primary" onClick={handlePdf} disabled={downloading}>{downloading ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}{downloading ? 'Preparing…' : 'Print my archive'}</button></div></div>
      {downloadError ? <p className="form-error dashboard-error"><AlertCircle size={15} /> {downloadError}</p> : null}
      <div className="dashboard-rule"><span>THE JOURNAL AT A GLANCE</span><span>NOTHING HERE IS GUESSED</span></div>
      <div className="metric-grid">
        <Metric label="Films in your archive" value={Number(basic.total_films || 0).toLocaleString()} note="Unique films watched" symbol={<Film size={15} />} />
        <Metric label="Screenings logged" value={Number(basic.total_diary_entries || 0).toLocaleString()} note="Diary entries, rewatches included" symbol={<CalendarDays size={15} />} />
        <Metric label="Your average rating" value={basic.average_rating ? Number(basic.average_rating).toFixed(2) + ' ★' : '—'} note="From your ratings" symbol={<Star size={15} />} />
        <Metric label="Longest streak" value={Number(pro.longest_watch_streak || 0) + ' days'} note="Consecutive days with a diary entry" symbol={<Clock3 size={15} />} />
      </div>
      {(stats.community_comparison?.top_rated || []).length ? <section className="top-four-section">
        <div className="top-four-heading">
          <div><div className="section-marker"><span>00</span><span>THE FILMS YOU RATED HIGHEST</span></div><h2>Four that <em>stay with you.</em></h2><p>Your highest-rated films from the ratings in this export. Your taste, your call.</p></div>
          <span className="top-four-note">PERSONAL FAVOURITES</span>
        </div>
        <div className="top-four-grid">
          {stats.community_comparison.top_rated.slice(0, 4).map((film, index) => <article className="top-four-card" key={film.title + '-' + film.year}>
            <div className="top-four-art"><MiniPoster film={film} size="featured" /><span className="top-four-index">0{index + 1}</span><span className="top-four-rating"><Star size={12} fill="currentColor" /> {Number(film.user_rating).toFixed(1)}</span></div>
            <div className="top-four-copy"><h3>{film.title}</h3><span>{film.year || 'Release year unknown'}</span></div>
          </article>)}
        </div>
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

function EmptyChart({ note }) {
  return <div className="empty-chart"><div className="empty-chart-icon"><Film size={22} /></div><p>{note}</p></div>;
}

function Footer({ onImport, dashboard = false }) {
  return (
    <footer className="site-footer section-shell" id="about">
      <div className="footer-top">
        <div className="footer-brand-block">
          <Brand onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} />
          <p className="footer-motto">Your personal<br /><em>cinematheque.</em></p>
        </div>
        <div className="footer-right">
          <span className="eyebrow">THE NEXT SCREENING</span>
          <button className="text-button" onClick={onImport}>{dashboard ? 'Add to your archive' : 'Open your archive'} <ArrowUpRight size={15} /></button>
          <a href="https://letterboxd.com/data/export/" target="_blank" rel="noreferrer">How to export Letterboxd <ArrowUpRight size={13} /></a>
          <div className="footer-socials" aria-label="Social links">
            <a className="footer-social-link footer-letterboxd-link" href="https://boxd.it/8hpsV" target="_blank" rel="noopener noreferrer" aria-label="Letterboxd profile" title="Letterboxd"><LetterboxdMark size={24} /></a>
            <a className="footer-social-link footer-github-link" href="https://github.com/tirthharshi-debug/CineStats-Next" target="_blank" rel="noopener noreferrer" aria-label="CineStats on GitHub" title="GitHub"><Github size={22} strokeWidth={1.8} /></a>
          </div>
        </div>
      </div>
      <div className="footer-bottom"><span>© 2026 CINESTATS</span><span>INDEPENDENT · UNOFFICIAL · FOR CINEPHILES</span></div>
    </footer>
  );
}

export default function App() {
  const [showImport, setShowImport] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [jobId, setJobId] = useState(null);

  const onComplete = useCallback((data, id) => {
    setDashboardData(data); setJobId(id); setShowImport(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const goHome = () => {
    setDashboardData(null); setJobId(null); window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  useEffect(() => {
    if (!showImport) return undefined;
    const handleKey = event => { if (event.key === 'Escape') setShowImport(false); };
    window.addEventListener('keydown', handleKey);
    document.body.classList.add('modal-open');
    return () => { window.removeEventListener('keydown', handleKey); document.body.classList.remove('modal-open'); };
  }, [showImport]);

  return (
    <div className="app-shell">
      <Header onImport={() => setShowImport(true)} onHome={goHome} dashboard={Boolean(dashboardData)} />
      {dashboardData ? <motion.div className="dashboard-reveal" initial={{ opacity: 0, y: 34, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 1.65, ease: [0.16, 1, 0.3, 1], opacity: { duration: 1.15 }, scale: { duration: 1.65, ease: [0.16, 1, 0.3, 1] } }}><span className="dashboard-reveal-light" aria-hidden="true" /><AnalyticsDashboard data={dashboardData} jobId={jobId} onImport={() => setShowImport(true)} onHome={goHome} /></motion.div> : <LandingPage onImport={() => setShowImport(true)} />}
      <Footer onImport={() => setShowImport(true)} dashboard={Boolean(dashboardData)} />
      <AnimatePresence>{showImport ? <UploadModal onClose={() => setShowImport(false)} onComplete={onComplete} /> : null}</AnimatePresence>
    </div>
  );
}
