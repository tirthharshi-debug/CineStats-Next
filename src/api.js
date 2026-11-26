import axios from 'axios';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '');

// Polling and results calls are quick; uploads of a 10 MB export on a slow
// connection need a much longer budget than the default.
const api = axios.create({ baseURL: API_BASE_URL, timeout: 30_000 });
const UPLOAD_TIMEOUT_MS = 180_000;
const EXPORT_TIMEOUT_MS = 90_000;

// Every job endpoint requires the secret token returned by the upload call.
const withToken = (token, extra = {}) => ({ ...extra, headers: { 'X-Job-Token': token } });

export async function uploadLetterboxdExport(file, onUploadProgress, signal) {
  const body = new FormData();
  body.append('file', file);
  const response = await api.post('/upload', body, {
    timeout: UPLOAD_TIMEOUT_MS,
    signal,
    onUploadProgress(event) {
      if (event.total && onUploadProgress) {
        onUploadProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
  return response.data;
}

export async function getJobProgress(jobId, token) {
  const response = await api.get(`/progress/${encodeURIComponent(jobId)}`, withToken(token));
  return response.data;
}

export async function getJobResults(jobId, token) {
  const response = await api.get(`/results/${encodeURIComponent(jobId)}`, withToken(token));
  return response.data;
}

export async function downloadReport(jobId, token) {
  const response = await api.get(
    `/export/pdf/${encodeURIComponent(jobId)}`,
    withToken(token, { responseType: 'blob', timeout: EXPORT_TIMEOUT_MS }),
  );
  return response.data;
}

export async function deleteJob(jobId, token) {
  const response = await api.delete(`/jobs/${encodeURIComponent(jobId)}`, withToken(token));
  return response.data;
}

/** Turn any axios/network failure into a short, human-readable sentence. */
export function describeApiError(err, fallback = 'Something went wrong. Please try again.') {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (status === 429) return 'CineStats is busy right now. Please wait a moment and try again.';
  if (status === 404) return 'This analysis is no longer available. It may have expired, so please upload your export again.';
  if (status === 413) return 'This file is too large. The limit is 10 MB.';
  if (err?.code === 'ECONNABORTED') return 'The request took too long. Check your connection and try again.';
  if (err?.request && !err?.response) return 'Could not reach the CineStats service. Check your connection and try again.';
  return err?.message || fallback;
}

export function retryAfterMs(err, fallbackMs = 5000) {
  const header = Number(err?.response?.headers?.['retry-after']);
  return Number.isFinite(header) && header > 0 ? Math.min(header, 60) * 1000 : fallbackMs;
}

export function getApiOrigin() {
  return API_BASE_URL;
}
