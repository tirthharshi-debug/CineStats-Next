import axios from 'axios';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '');
const api = axios.create({ baseURL: API_BASE_URL, timeout: 30_000 });

export async function uploadLetterboxdExport(file, onUploadProgress) {
  const body = new FormData();
  body.append('file', file);
  const response = await api.post('/upload', body, {
    onUploadProgress(event) {
      if (event.total && onUploadProgress) {
        onUploadProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
  return response.data;
}

export async function getJobProgress(jobId, jobToken) {
  const response = await api.get(`/progress/${encodeURIComponent(jobId)}`, {
    headers: { 'X-Job-Token': jobToken },
  });
  return response.data;
}

export async function getJobResults(jobId, jobToken) {
  const response = await api.get(`/results/${encodeURIComponent(jobId)}`, {
    headers: { 'X-Job-Token': jobToken },
  });
  return response.data;
}

export async function downloadReport(jobId, jobToken) {
  const response = await api.get(`/export/pdf/${encodeURIComponent(jobId)}`, {
    responseType: 'blob',
    headers: { 'X-Job-Token': jobToken },
  });
  return response.data;
}

export function getApiOrigin() {
  return API_BASE_URL;
}
