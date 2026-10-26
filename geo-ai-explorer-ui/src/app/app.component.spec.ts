import { TestBed } from '@angular/core/testing';
import { provideMockStore } from '@ngrx/store/testing';

import { AppComponent } from './app.component';
import { getWorkflowStep, WorkflowStep } from './state/explorer.state';

describe('AppComponent', () => {
  beforeEach(async () => {
    localStorage.removeItem('geo-ai-explorer-theme');
    document.documentElement.classList.remove('app-dark');

    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideMockStore({ selectors: [{ selector: getWorkflowStep, value: WorkflowStep.FullScreenChat }] })],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should toggle and persist dark mode', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const initialMode = app.isDarkMode;

    app.toggleTheme();

    expect(app.isDarkMode).toBe(!initialMode);
    expect(document.documentElement.classList.contains('app-dark')).toBe(!initialMode);
    expect(localStorage.getItem('geo-ai-explorer-theme')).toBe(!initialMode ? 'dark' : 'light');
  });

  it('should not show the storage error banner when localStorage works', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.storage-error')).toBeNull();
  });

  it('should show the storage error banner when localStorage fails', () => {
    spyOn(Storage.prototype, 'setItem').and.throwError('The quota has been exceeded.');

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const banner: HTMLElement = fixture.nativeElement.querySelector('.storage-error');

    expect(banner).not.toBeNull();
    expect(banner.textContent).toContain('Browser storage is unavailable');
    expect(banner.textContent).toContain('The quota has been exceeded.');
  });
});
