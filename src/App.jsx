import { Component, Suspense, lazy, useCallback, useEffect, useId, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays,
  Clapperboard, Github, Heart, Menu, Star, Ticket, Upload, X,
} from 'lucide-react';
import { describeApiError, getJobProgress, getJobResults, retryAfterMs, uploadLetterboxdExport } from './api';

// The dashboard (and the charting library it pulls in) loads only after an
// analysis finishes, which keeps the landing page fast.
const AnalyticsDashboard = lazy(() => import('./Dashboard.jsx'));

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
  const [logoFailed, setLogoFailed] = useState(false);
  return (
    <button className="brand" onClick={onClick} aria-label="CineStats home">
      {logoFailed
        ? <span className="brand-fallback"><Clapperboard size={22} strokeWidth={1.6} /><span>CineStats</span></span>
        : <img className="brand-logo-image" src="/images/cinestats-logo.webp" alt="CineStats" onError={() => setLogoFailed(true)} />}
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
  const uploadController = useRef(null);

  useEffect(() => () => {
    cancelled.current = true;
    uploadController.current?.abort();
  }, []);

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
      setError('This file is over 10 MB. The current upload service accepts exports up to 10 MB.');
      return;
    }
    setFile(candidate);
  };

  const processFile = async () => {
    if (!file || phase === 'uploading' || phase === 'processing') return;
    cancelled.current = false;
    uploadController.current?.abort();
    const controller = new AbortController();
    uploadController.current = controller;
    setError('');
    setPhase('uploading');
    setUploadProgress(0);
    try {
      const started = await uploadLetterboxdExport(file, setUploadProgress, controller.signal);
      if (!started?.job_id || !started?.job_token) throw new Error('The analysis service did not return a job ID.');
      const { job_id: jobId, job_token: jobToken } = started;
      setPhase('processing');
      let attempts = 0;
      let consecutiveFailures = 0;
      while (!cancelled.current && attempts < 900) {
        attempts += 1;
        let progress;
        try {
          progress = await getJobProgress(jobId, jobToken);
          consecutiveFailures = 0;
        } catch (pollError) {
          // A dropped connection or a busy server should not abandon a running analysis.
          const status = pollError?.response?.status;
          consecutiveFailures += 1;
          if (status === 404 || consecutiveFailures >= 5) throw pollError;
          await new Promise(resolve => window.setTimeout(resolve, retryAfterMs(pollError, 3000)));
          continue;
        }
        setJobProgress(progress);
        if (progress.status === 'error') throw new Error(progress.error || 'The analysis could not be completed.');
        if (progress.status === 'done') {
          const result = await getJobResults(jobId, jobToken);
          if (!result?.stats) throw new Error('The API returned no analytics data.');
          onComplete(result, jobId, jobToken);
          return;
        }
        await new Promise(resolve => window.setTimeout(resolve, 1300));
      }
      if (!cancelled.current) throw new Error('This analysis is taking longer than expected. Please try again.');
    } catch (err) {
      if (!cancelled.current && err?.code !== 'ERR_CANCELED') {
        setError(describeApiError(err, 'Something went wrong while reading your archive.'));
        setPhase('idle');
      }
    } finally {
      uploadController.current = null;
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
            <p className="privacy-note">Your export is processed on the CineStats server, never shared, and your results are deleted automatically after about 30 minutes. Matched films are enriched with metadata, community ratings and poster artwork using the <a href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer">TMDB API</a>.</p>
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
            <span className="eyebrow"><span className="live-dot" /> {phase === 'uploading' ? 'THE REEL IS ARRIVING' : jobProgress.status === 'queued' ? 'IN THE SCREENING QUEUE' : jobProgress.status === 'enriching' ? 'IN THE CUTTING ROOM' : 'READING YOUR FILM DIARY'}</span>
            <h3 key={phase === 'uploading' ? 'uploading' : jobProgress.status === 'queued' ? 'queued' : messageIndex} className="intermission-title">{phase === 'uploading' ? 'Getting your archive on screen.' : jobProgress.status === 'queued' ? 'Waiting for an open projector.' : intermission.title}</h3>
            <p className="intermission-note">{phase === 'uploading' ? 'Sending your Letterboxd export to the analysis service.' : jobProgress.status === 'queued' ? 'CineStats is finishing another archive ahead of yours. Your upload is queued and will start automatically.' : intermission.note}</p>
            <div className="intermission-stage"><span className={phase === 'uploading' ? 'stage-active' : 'stage-done'}>01 <i>THE EXPORT</i></span><span className={phase === 'processing' ? 'stage-active' : ''}>02 <i>THE ARCHIVE</i></span><span>03 <i>THE REVEAL</i></span></div>
            <div className="progress-track"><span style={{ width: (phase === 'uploading' ? uploadProgress : movieCount) + '%' }} /></div>
            <div className="progress-label"><span>{phase === 'uploading' ? uploadProgress + '% uploaded' : jobProgress.status === 'queued' ? 'Queued — starting automatically' : (jobProgress.current + ' / ' + jobProgress.total + ' titles enriched')}</span><span>{phase === 'processing' && movieCount ? movieCount + '%' : ''}</span></div>
            {error ? <p className="form-error"><AlertCircle size={15} /> {error}</p> : null}
            <button className="text-button" onClick={() => { cancelled.current = true; uploadController.current?.abort(); setPhase('idle'); setError('Processing stopped in this window. The server job may continue until it expires.'); }}>Stop waiting <ArrowRight size={14} /></button>
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
          <div className="eyebrow hero-eyebrow"><span className="eyebrow-line" /> A HOME FOR YOUR FILM LIFE </div>
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
              onError={event => { event.currentTarget.style.display = 'none'; }}
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
            <a className="footer-social-link footer-github-link" href="https://github.com/tirthharshi-debug/CineStats" target="_blank" rel="noopener noreferrer" aria-label="CineStats on GitHub" title="GitHub"><Github size={22} strokeWidth={1.8} /></a>
          </div>
        </div>
      </div>
      <div className="tmdb-attribution" aria-label="TMDB attribution">
        <p>Film metadata and poster images provided by <a href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer">TMDB</a>.</p>
        <p>This product uses the TMDB API but is not endorsed or certified by TMDB. <a href="https://www.themoviedb.org/about/logos-attribution" target="_blank" rel="noopener noreferrer">TMDB logo and attribution guidelines <ArrowUpRight size={12} /></a></p>
      </div>
      <div className="footer-bottom"><span>© 2026 CINESTATS</span><span>INDEPENDENT · UNOFFICIAL · FOR CINEPHILES</span></div>
      <p className="tmdb-attribution">This product uses the TMDB API but is not endorsed or certified by TMDB. Letterboxd is a trademark of its owners; CineStats is not affiliated with Letterboxd.</p>
    </footer>
  );
}

export class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false }; }
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.error('CineStats UI error:', error); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="section-shell route-loading" role="alert">
        <h1>Something <em>slipped.</em></h1>
        <p>CineStats hit an unexpected problem displaying this page. Your data was not lost on our side, but you may need to reload and upload your export again.</p>
        <button className="button button-primary" onClick={() => window.location.reload()}>Reload CineStats</button>
      </main>
    );
  }
}

export default function App() {
  const [showImport, setShowImport] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobToken, setJobToken] = useState(null);

  const onComplete = useCallback((data, id, token) => {
    setDashboardData(data); setJobId(id); setJobToken(token); setShowImport(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const goHome = () => {
    setDashboardData(null); setJobId(null); setJobToken(null); window.scrollTo({ top: 0, behavior: 'smooth' });
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
      {dashboardData ? <motion.div className="dashboard-reveal" initial={{ opacity: 0, y: 34, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 1.65, ease: [0.16, 1, 0.3, 1], opacity: { duration: 1.15 }, scale: { duration: 1.65, ease: [0.16, 1, 0.3, 1] } }}><span className="dashboard-reveal-light" aria-hidden="true" /><Suspense fallback={<main className="dashboard section-shell route-loading">Preparing your archive…</main>}><AnalyticsDashboard data={dashboardData} jobId={jobId} jobToken={jobToken} onImport={() => setShowImport(true)} onHome={goHome} /></Suspense></motion.div> : <LandingPage onImport={() => setShowImport(true)} />}
      <Footer onImport={() => setShowImport(true)} dashboard={Boolean(dashboardData)} />
      <AnimatePresence>{showImport ? <UploadModal onClose={() => setShowImport(false)} onComplete={onComplete} /> : null}</AnimatePresence>
    </div>
  );
}
