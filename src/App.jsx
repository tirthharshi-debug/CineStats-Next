import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
const filmsToDiscover = [
  { title: 'In the Mood for Love', year: '2000', director: 'Wong Kar-wai', mark: '01', tone: 'rose' },
  { title: 'Perfect Days', year: '2023', director: 'Wim Wenders', mark: '02', tone: 'moss' },
  { title: 'Aftersun', year: '2022', director: 'Charlotte Wells', mark: '03', tone: 'blue' },
  { title: 'Chungking Express', year: '1994', director: 'Wong Kar-wai', mark: '04', tone: 'amber' },
];

function Brand({ onClick }) {
  return (
    <button className="brand" onClick={onClick} aria-label="CineStats home">
      <span className="brand-mark"><Clapperboard size={21} strokeWidth={1.7} /></span>
      <span className="brand-word">cine<span>stats</span><small>THE PERSONAL CINEMATHEQUE</small></span>
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

function PosterArtwork({ film, index }) {
  return (
    <div className={'poster-art poster-' + film.tone}>
      <div className="poster-grain" />
      <span className="poster-number">{film.mark}</span>
      <div className="poster-graphic">
        {index === 0 ? <><span className="orb orb-one" /><span className="orb orb-two" /><span className="poster-vertical">LOVE IS A MATTER OF TIMING</span></> : null}
        {index === 1 ? <><span className="window-shape" /><span className="sun-shape" /><span className="poster-vertical">THE BEAUTY OF THE EVERYDAY</span></> : null}
        {index === 2 ? <><span className="horizon-shape" /><span className="poster-sun" /><span className="poster-vertical">REMEMBER HOW IT FELT</span></> : null}
        {index === 3 ? <><span className="neon-block" /><span className="neon-line" /><span className="poster-vertical">LOST IN THE CITY</span></> : null}
      </div>
      <div className="poster-caption">
        <span className="poster-kicker">A FILM BY {film.director.toUpperCase()}</span>
        <span className="poster-title">{film.title}</span>
        <span className="poster-year">{film.year} · CINEMA FOREVER</span>
      </div>
    </div>
  );
}

function FilmCard({ film, index }) {
  return (
    <article className="film-card">
      <div className="film-art-wrap"><PosterArtwork film={film} index={index} /></div>
      <div className="film-card-meta">
        <div><h3>{film.title}</h3><p>{film.director}</p></div>
        <span className="film-year">{film.year}</span>
      </div>
    </article>
  );
}

function UploadModal({ onClose, onComplete }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobProgress, setJobProgress] = useState({ status: 'idle', current: 0, total: 0 });
  const [error, setError] = useState('');
  const inputRef = useRef(null);
  const cancelled = useRef(false);

  useEffect(() => () => { cancelled.current = true; }, []);

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

  const working = phase === 'uploading' || phase === 'processing';
  const movieCount = jobProgress.total > 0 ? Math.min(100, Math.round((jobProgress.current / jobProgress.total) * 100)) : 0;

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
          <div className="processing-panel">
            <div className="processing-reel"><LoaderCircle size={31} strokeWidth={1.3} /></div>
            <span className="eyebrow">{phase === 'uploading' ? 'SENDING THE REEL' : 'IN THE CUTTING ROOM'}</span>
            <h3>{phase === 'uploading' ? 'Getting your archive on screen.' : 'Finding the shape of your taste.'}</h3>
            <p>{phase === 'uploading' ? 'Uploading your export to the configured API.' : jobProgress.status === 'enriching' ? 'Matching films, one frame at a time.' : 'Reading your diary and preparing your stats.'}</p>
            <div className="progress-track"><span style={{ width: (phase === 'uploading' ? uploadProgress : movieCount) + '%' }} /></div>
            <div className="progress-label"><span>{phase === 'uploading' ? uploadProgress + '% uploaded' : (jobProgress.current + ' / ' + jobProgress.total + ' titles enriched')}</span><span>{phase === 'processing' && movieCount ? movieCount + '%' : ''}</span></div>
            {error ? <p className="form-error"><AlertCircle size={15} /> {error}</p> : null}
            <button className="text-button" onClick={() => { cancelled.current = true; setPhase('idle'); setError('Processing stopped in this window. The server job may continue until it expires.'); }}>Stop waiting</button>
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

      <section className="archive-section" id="archive">
        <div className="section-shell">
          <div className="archive-heading"><div><div className="section-marker"><span>02</span><span>A FEW FRAMES TO BEGIN</span></div><h2>For the love<br />of <em>the image.</em></h2></div><p className="archive-intro">Every collection is personal. Start with the films you have seen; let the patterns surprise you.</p></div>
          <div className="film-grid">{filmsToDiscover.map((film, index) => <FilmCard key={film.title} film={film} index={index} />)}</div>
          <div className="archive-bottom"><span><span className="small-dot" /> AN OPENING REEL, NOT YOUR DATA</span><button className="text-button" onClick={onImport}>Bring in your own films <ArrowRight size={15} /></button></div>
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
      <div className="dashboard-masthead"><div><div className="eyebrow"><span className="eyebrow-line" /> YOUR CINEMATHEQUE / PRIVATE EDITION</div><h1>The story so<br /><em>far.</em></h1><p className="dashboard-intro">An archive of the films you've met along the way. This is your viewing life, made visible.</p></div><div className="dashboard-actions"><button className="button button-outline" onClick={onImport}><Upload size={15} /> Add an export</button><button className="button button-primary" onClick={handlePdf} disabled={downloading}>{downloading ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}{downloading ? 'Preparing…' : 'Print my archive'}</button></div></div>
      {downloadError ? <p className="form-error dashboard-error"><AlertCircle size={15} /> {downloadError}</p> : null}
      <div className="dashboard-rule"><span>THE ARCHIVE AT A GLANCE</span><span>NOTHING HERE IS GUESSED</span></div>
      <div className="metric-grid">
        <Metric label="Films in your archive" value={Number(basic.total_films || 0).toLocaleString()} note="Unique films watched" symbol={<Film size={15} />} />
        <Metric label="Screenings logged" value={Number(basic.total_diary_entries || 0).toLocaleString()} note="Diary entries, rewatches included" symbol={<CalendarDays size={15} />} />
        <Metric label="Your average rating" value={basic.average_rating ? Number(basic.average_rating).toFixed(2) + ' ★' : '—'} note="From your ratings" symbol={<Star size={15} />} />
        <Metric label="Longest streak" value={Number(pro.longest_watch_streak || 0) + ' days'} note="Consecutive days with a diary entry" symbol={<Clock3 size={15} />} />
      </div>
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
      <div className="footer-top"><div><Brand onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} /><p className="footer-motto">For the films that made us.<br /><em>And the ones still waiting.</em></p></div><div className="footer-right"><span className="eyebrow">THE NEXT SCREENING</span><button className="text-button" onClick={onImport}>{dashboard ? 'Add to your archive' : 'Open your archive'} <ArrowUpRight size={15} /></button><a href="https://letterboxd.com/data/export/" target="_blank" rel="noreferrer">How to export Letterboxd <ArrowUpRight size={13} /></a><a href="https://github.com/tirthharshi-debug/CineStats-Next" target="_blank" rel="noreferrer"><Github size={14} /> Project on GitHub</a></div></div>
      <div className="footer-bottom"><span>© 2026 CINESTATS NEXT · BUILT WITH FEELING</span><span>INDEPENDENT · UNOFFICIAL · FOR CINEPHILES</span></div>
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
      {dashboardData ? <AnalyticsDashboard data={dashboardData} jobId={jobId} onImport={() => setShowImport(true)} onHome={goHome} /> : <LandingPage onImport={() => setShowImport(true)} />}
      <Footer onImport={() => setShowImport(true)} dashboard={Boolean(dashboardData)} />
      <AnimatePresence>{showImport ? <UploadModal onClose={() => setShowImport(false)} onComplete={onComplete} /> : null}</AnimatePresence>
    </div>
  );
}
