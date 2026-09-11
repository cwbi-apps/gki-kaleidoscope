import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom, timeout } from 'rxjs';

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
 *
 * Error recovery: a single hung status request (one that never resolves or
 * rejects -- e.g. a dropped connection that never produces a response)
 * used to be able to leave the caller waiting forever, since the elapsed
 * time was only ever checked after a response came back. There's now a hard
 * wall-clock deadline (`deadlineTimer` below) that fires independently of
 * whether any individual request ever completes, so a poll can never hang
 * past MAX_POLL_DURATION_MS. Individual requests also carry their own
 * timeout so one slow/dead request doesn't block the next retry. A
 * definitive "job not found" response (see AsyncJobService#getStatus on
 * the server) fails fast, since that means the server has restarted or
 * otherwise lost track of the job and there's nothing left to wait for;
 * any other error (a transient network blip, a 5xx from the load
 * balancer, ...) is treated as retryable and polling continues until the
 * deadline.
 */

const POLL_INTERVAL_MS = 2000;

// Guards a single status request against hanging indefinitely (e.g. a
// dropped connection that never produces a response or an error).
const REQUEST_TIMEOUT_MS = 15 * 1000;

// Absolute wall-clock budget for the whole poll, independent of how many
// individual requests succeed, fail, or hang along the way. Matches (with a
// little headroom over) the server's own job watchdog -- see
// AsyncJobService.MAX_JOB_DURATION_MILLIS -- so the server should normally
// report FAILED first, with this as the last-resort backstop.
const MAX_POLL_DURATION_MS = 15 * 60 * 1000;

function timeoutError(statusUrl: string): HttpErrorResponse {
  return new HttpErrorResponse({
    error: 'The request took too long to complete. Please try again.',
    status: 408,
    statusText: 'Request Timeout',
    url: statusUrl
  });
}

export function pollJob<T>(http: HttpClient, statusUrl: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;

    // Fires even if a poll request never resolves or rejects, which the
    // in-loop elapsed-time check below can't catch on its own since it only
    // runs once a response has actually arrived.
    const deadlineTimer = setTimeout(() => {
      settle(() => reject(timeoutError(statusUrl)));
    }, MAX_POLL_DURATION_MS);

    function settle(action: () => void): void {
      if (settled) {
        return;
      }

      settled = true;
      clearTimeout(deadlineTimer);
      action();
    }

    function poll(): void {
      firstValueFrom(http.get<JobStatusResponse<T>>(statusUrl).pipe(timeout(REQUEST_TIMEOUT_MS)))
        .then(status => {
          if (status.status === 'SUCCEEDED') {
            settle(() => resolve(status.result as T));
            return;
          }

          if (status.status === 'FAILED') {
            settle(() => reject(new HttpErrorResponse({
              error: status.errorMessage || 'Your request failed to complete',
              status: 400,
              statusText: 'Bad Request',
              url: statusUrl
            })));
            return;
          }

          setTimeout(poll, POLL_INTERVAL_MS);
        })
        .catch(error => {
          // A definitive "job not found" (see AsyncJobService#getStatus)
          // means the server restarted or otherwise lost track of the job
          // -- there's nothing left to poll for, so fail immediately
          // instead of waiting out the rest of the deadline.
          if (error instanceof HttpErrorResponse && error.status === 400) {
            settle(() => reject(error));
            return;
          }

          // Anything else (a request timeout, a transient network error, a
          // 5xx from the load balancer, ...) is treated as retryable.
          setTimeout(poll, POLL_INTERVAL_MS);
        });
    }

    poll();
  });
}
