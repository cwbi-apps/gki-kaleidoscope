/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { EnvironmentProviders, Provider } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { provideStore } from '@ngrx/store';
import { MessageService } from 'primeng/api';
import { providePrimeNG } from 'primeng/config';

import { chatReducer } from '../state/chat.state';
import { explorerReducer } from '../state/explorer.state';

/**
 * The app-wide providers from app.config.ts, with HTTP requests captured by
 * HttpTestingController instead of reaching the server.
 */
export function provideTestApp(): (Provider | EnvironmentProviders)[] {
    return [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        providePrimeNG(),
        provideStore({
            chat: chatReducer,
            explorer: explorerReducer
        }),
        MessageService,
    ];
}
