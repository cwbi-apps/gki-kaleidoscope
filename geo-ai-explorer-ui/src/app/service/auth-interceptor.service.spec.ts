import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { authInterceptor, readCsrfToken } from './auth-interceptor.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpTesting: HttpTestingController;

  const setCookie = (value: string): void => {
    document.cookie = 'XSRF-TOKEN=' + encodeURIComponent(value) + '; path=/';
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting()
      ]
    });

    http = TestBed.inject(HttpClient);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    document.cookie = 'XSRF-TOKEN=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('does not add the token to GET requests', () => {
    setCookie('abc');

    http.get('api/test').subscribe();

    expect(httpTesting.expectOne('api/test').request.headers.has('X-XSRF-TOKEN')).toBeFalse();
  });

  it('adds the cookie token to same-origin POST requests', () => {
    setCookie('abc');

    const url = window.location.origin + '/api/test';
    http.post(url, {}).subscribe();

    expect(httpTesting.expectOne(url).request.headers.get('X-XSRF-TOKEN')).toBe('abc');
  });

  it('does not send the token to other origins', () => {
    setCookie('abc');

    http.post('https://example.com/api/test', {}).subscribe();

    expect(httpTesting.expectOne('https://example.com/api/test').request.headers.has('X-XSRF-TOKEN')).toBeFalse();
  });

  it('always sends the current cookie value', () => {
    setCookie('first');
    http.post('api/one', {}).subscribe();

    // e.g. the server rotated the token on login
    setCookie('second');
    http.post('api/two', {}).subscribe();

    expect(httpTesting.expectOne('api/one').request.headers.get('X-XSRF-TOKEN')).toBe('first');
    expect(httpTesting.expectOne('api/two').request.headers.get('X-XSRF-TOKEN')).toBe('second');
  });

  it('does not depend on localStorage', () => {
    spyOn(Storage.prototype, 'setItem').and.throwError('QuotaExceededError');
    spyOn(Storage.prototype, 'getItem').and.throwError('SecurityError');

    setCookie('abc');

    http.post('api/test', {}).subscribe();

    expect(httpTesting.expectOne('api/test').request.headers.get('X-XSRF-TOKEN')).toBe('abc');
  });

  it('reads an encoded cookie value', () => {
    setCookie('a/b+c=');

    expect(readCsrfToken()).toBe('a/b+c=');
  });
});
