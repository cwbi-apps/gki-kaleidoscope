import { environment } from '../../environments/environment';

/**
 * Returns the absolute base URL of the API server, always ending in '/'.
 *
 * environment.apiUrl may be absolute (dev: 'http://localhost:8080/') or empty
 * (prod: same origin as the UI). When it is empty or relative it is resolved
 * against document.baseURI, i.e. the <base href> the server injects into
 * index.html, so the app works under any servlet context path (e.g.
 * '/kaleidoscope/').
 *
 * The result is always absolute because some consumers (MapLibre tile / glyph
 * templates, which are fetched from web workers) can't resolve relative URLs.
 *
 * Callers concatenate onto this rather than using `new URL(path, base)`
 * because the URL parser percent-encodes '{' and '}', which would break
 * MapLibre templates like '{z}/{x}/{y}'.
 */
export function apiBase(): string {
  const base = new URL(environment.apiUrl || '.', document.baseURI).href;

  return base.endsWith('/') ? base : base + '/';
}
