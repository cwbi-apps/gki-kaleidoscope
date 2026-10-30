/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { MessageService } from 'primeng/api';

@Injectable({
  providedIn: 'root',
})
export class ErrorService {

  private sessionExpiredShown = false;

  constructor(private messageService: MessageService) {
  }


  handleError(response: HttpErrorResponse) {
    if (response.status === 0) {
      this.messageService.add({
        key: 'explorer',
        severity: 'error',
        summary: 'Error',
        detail: 'Unable to communicate with the server',
        sticky: true
      })
    }
    else if (response.status === 401) {
      // The server returns 401 for API calls without a valid session. Show
      // this once instead of once per request.
      if (!this.sessionExpiredShown) {
        this.sessionExpiredShown = true;

        this.messageService.add({
          key: 'session',
          severity: 'warn',
          summary: 'Session expired',
          detail: 'Your session has expired. Please log in again.',
          sticky: true,
          closable: false
        })
      }
    }
    else if (response.status === 403) {
      // Not a login problem (that's a 401). Usually a web application firewall
      // in front of the app rejecting the request's content, e.g. query text
      // such as SQL or SPARQL in a chat message.
      this.messageService.add({
        key: 'explorer',
        severity: 'error',
        summary: 'Request blocked',
        detail: 'This request was blocked by a network security filter. If your message includes query or code text (e.g. SQL or SPARQL), try rephrasing it. If the problem continues, contact your administrator.',
        sticky: true
      })
    }
    else if (response.status === 400 || response.status === 500) {

      let message = 'Your request failed to complete';

      if (typeof response.error === 'string' && response.error !== null) {
        message = response.error;
      }
      else if (typeof response.error === 'object' && response.error !== null) {
        message = response.error.error;
      }

      this.messageService.add({
        key: 'explorer',
        severity: 'error',
        summary: 'Error',
        detail: message,
        sticky: true

      })
    }

  }

}