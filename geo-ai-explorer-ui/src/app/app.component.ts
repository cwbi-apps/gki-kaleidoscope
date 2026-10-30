/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */

import { Component, inject, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RouterOutlet } from '@angular/router';
import { TooltipModule } from 'primeng/tooltip';
import { Store } from '@ngrx/store';
import { Subscription } from 'rxjs';

import { getWorkflowStep, WorkflowStep } from './state/explorer.state';
import { checkLocalStorage, StorageCheckResult } from './service/storage-check.util';
import { apiBase } from './service/url.util';

@Component({
    selector: 'app-root',
    imports: [RouterOutlet, TooltipModule],
    templateUrl: './app.component.html',
    styleUrl: './app.component.scss'
})
export class AppComponent implements OnDestroy {
    private readonly store = inject(Store);
    private readonly http = inject(HttpClient);
    private readonly storageKey = 'geo-ai-explorer-theme';
    private readonly systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    private readonly onSystemThemeChange = (event: MediaQueryListEvent): void => {
        if (!this.storageCheck.ok || !localStorage.getItem(this.storageKey)) {
            this.setDarkMode(event.matches);
        }
    };
    private readonly onWorkflowStepChange: Subscription;

    // Checked first so the error banner can still render if localStorage throws
    readonly storageCheck: StorageCheckResult = checkLocalStorage();

    isDarkMode = document.documentElement.classList.contains('app-dark');

    // The theme toggle and logout button are only shown on the chat-only views (full-screen chat
    // / chat + results). It's hidden everywhere the map is visible.
    isChatOnlyView = true;

    constructor() {
        const savedTheme = this.storageCheck.ok ? localStorage.getItem(this.storageKey) : null;
        this.setDarkMode(savedTheme ? savedTheme === 'dark' : this.systemTheme.matches);
        this.systemTheme.addEventListener('change', this.onSystemThemeChange);

        this.onWorkflowStepChange = this.store.select(getWorkflowStep).subscribe(step => {
            this.isChatOnlyView = step === WorkflowStep.FullScreenChat || step === WorkflowStep.AiChatAndResults;
        });
    }

    toggleTheme(): void {
        this.setDarkMode(!this.isDarkMode);

        if (this.storageCheck.ok) {
            localStorage.setItem(this.storageKey, this.isDarkMode ? 'dark' : 'light');
        }
    }

    logout(): void {
        // Spring Security only logs out on a POST to /logout carrying the CSRF
        // token. HttpClient sends it as a header (see authInterceptor). Go to the
        // login page either way: if the session already expired the logout is
        // rejected, but the user is logged out regardless.
        const toLogin = (): void => this.navigate(apiBase() + 'login?logout');

        this.http.post(apiBase() + 'logout', null, { responseType: 'text' }).subscribe({ next: toLogin, error: toLogin });
    }

    navigate(url: string): void {
        window.location.assign(url);
    }

    ngOnDestroy(): void {
        this.systemTheme.removeEventListener('change', this.onSystemThemeChange);
        this.onWorkflowStepChange.unsubscribe();
    }

    private setDarkMode(enabled: boolean): void {
        this.isDarkMode = enabled;
        document.documentElement.classList.toggle('app-dark', enabled);
        document.documentElement.style.colorScheme = enabled ? 'dark' : 'light';
    }
}
