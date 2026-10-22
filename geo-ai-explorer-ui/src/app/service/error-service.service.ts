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
    else if (response.status === 403) {
      // Every endpoint only requires a login, so a 403 means the session (and
      // its CSRF token) is gone. Show this once instead of once per request.
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