import { HttpInterceptorFn } from '@angular/common/http';

// Spring Security only checks the CSRF token on state-changing requests
const SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS', 'TRACE'];

/**
 * Reads the CSRF token from the XSRF-TOKEN cookie set by the server. The
 * browser keeps the cookie in sync with the server session, so it is read on
 * every request rather than cached.
 */
export function readCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]*)/);

  return match ? decodeURIComponent(match[1]) : null;
}

function isSameOrigin(url: string): boolean {
  return new URL(url, document.baseURI).origin === window.location.origin;
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (SAFE_METHODS.includes(req.method) || !isSameOrigin(req.url)) {
    return next(req);
  }

  const token = readCsrfToken();

  if (token != null) {
    // Add CSRF header
    return next(req.clone({
      setHeaders: {
        'X-XSRF-TOKEN': token
      }
    }));
  }

  return next(req);
};
