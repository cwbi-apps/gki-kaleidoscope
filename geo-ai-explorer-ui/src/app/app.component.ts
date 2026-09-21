import { NgIf } from '@angular/common';
import { Component, inject, OnDestroy } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { TooltipModule } from 'primeng/tooltip';
import { Store } from '@ngrx/store';
import { Subscription } from 'rxjs';

import { getWorkflowStep, WorkflowStep } from './state/explorer.state';

@Component({
    selector: 'app-root',
    imports: [RouterOutlet, NgIf, TooltipModule],
    templateUrl: './app.component.html',
    styleUrl: './app.component.scss'
})
export class AppComponent implements OnDestroy {
    private readonly store = inject(Store);
    private readonly storageKey = 'geo-ai-explorer-theme';
    private readonly systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    private readonly onSystemThemeChange = (event: MediaQueryListEvent): void => {
        if (!localStorage.getItem(this.storageKey)) {
            this.setDarkMode(event.matches);
        }
    };
    private readonly onWorkflowStepChange: Subscription;

    isDarkMode = document.documentElement.classList.contains('app-dark');

    // The theme toggle is only shown on the chat-only views (full-screen chat
    // / chat + results). It's hidden everywhere the map is visible.
    isChatOnlyView = true;

    constructor() {
        const savedTheme = localStorage.getItem(this.storageKey);
        this.setDarkMode(savedTheme ? savedTheme === 'dark' : this.systemTheme.matches);
        this.systemTheme.addEventListener('change', this.onSystemThemeChange);

        this.onWorkflowStepChange = this.store.select(getWorkflowStep).subscribe(step => {
            this.isChatOnlyView = step === WorkflowStep.FullScreenChat || step === WorkflowStep.AiChatAndResults;
        });
    }

    toggleTheme(): void {
        this.setDarkMode(!this.isDarkMode);
        localStorage.setItem(this.storageKey, this.isDarkMode ? 'dark' : 'light');
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
