import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { JobStatusResponse } from '../models/chat.model';

/*
 * Shared polling helper for the background-job endpoints (chat/prompt,
 * chat/get-locations, neighbors, ...). These endpoints run a slow
 * operation (a Bedrock AgentCore call, or a large SPARQL graph query) on
 * a background thread and return a job id immediately instead of blocking
 * the HTTP request thread -- which was exceeding the ALB's 60 second idle
 * timeout and producing 504 Gateway Timeout errors.
 *
 * This polls the job's status endpoint until it SUCCEEDS (resolving with
 * its result) or FAILS (rejecting with an HttpErrorResponse shaped just
 * like the error the old synchronous endpoint would have produced, so
 * existing `.catch(error => this.errorService.handleError(error))` call
 * sites keep working unchanged).
 */

const POLL_INTERVAL_MS = 2000;

// Comfortably longer than the server's longest expected job duration.
const MAX_POLL_DURATION_MS = 6 * 60 * 1000;

export function pollJob<T>(http: HttpClient, statusUrl: string): Promise<T> {
  const startedAt = Date.now();

  return new Promise<T>((resolve, reject) => {
    const poll = () => {
      firstValueFrom(http.get<JobStatusResponse<T>>(statusUrl))
        .then(status => {
          if (status.status === 'SUCCEEDED') {
            resolve(status.result as T);
            return;
          }

          if (status.status === 'FAILED') {
            reject(new HttpErrorResponse({
              error: status.errorMessage || 'Your request failed to complete',
              status: 400,
              statusText: 'Bad Request',
              url: statusUrl
            }));
            return;
          }

          if (Date.now() - startedAt > MAX_POLL_DURATION_MS) {
            reject(new HttpErrorResponse({
              error: 'The request took too long to complete. Please try again.',
              status: 408,
              statusText: 'Request Timeout',
              url: statusUrl
            }));
            return;
          }

          setTimeout(poll, POLL_INTERVAL_MS);
        })
        .catch(reject);
    };

    poll();
  });
}
