import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { v4 as uuidv4 } from 'uuid';

import { ChatMessage, JobStartResponse, LocationPage, ServerChatResponse } from '../models/chat.model';
import { MockUtil } from '../mock-util';
import { environment } from '../../environments/environment';
import { GeoObject } from '../models/geoobject.model';
import { ExplorerSessionStateService } from './explorer-session-state.service';
import { pollJob } from './job-polling.util';

@Injectable({
  providedIn: 'root',
})
export class ChatService {

  /*
   * chat/prompt and chat/get-locations both invoke a Bedrock AgentCore
   * harness on the server that can take up to several minutes to respond
   * -- well beyond the ALB's 60 second idle timeout, which was causing
   * 504 Gateway Timeout errors. Instead of waiting on a single long HTTP
   * request, the server now kicks the work off in the background and
   * returns a job id immediately; we poll its status here (see
   * job-polling.util.ts) until it completes. This is all internal to this
   * service -- callers still get back a Promise that resolves/rejects
   * exactly as before, so the busy spinner and every other bit of UI/UX
   * driven off that Promise needs no changes.
   */

  constructor(
    private http: HttpClient,
    private explorerSessionState: ExplorerSessionStateService
  ) {
  }


  sendMessage(sessionId: string, message: ChatMessage): Promise<ChatMessage> {

    if (environment.mockRequests)
    {
      return new Promise<ChatMessage>((resolve) => {
        setTimeout(() => {
          resolve(MockUtil.message);
        }, 500); // Simulating network delay
      });
    }
    else
    {
      let params = new HttpParams();
      params = params.append("sessionId", sessionId);
      params = params.append("prompt", message.text);

      return firstValueFrom(this.http.get<JobStartResponse>(environment.apiUrl + 'api/chat/prompt/start', { params }))
        .then(({ jobId }) => pollJob<ServerChatResponse>(this.http, environment.apiUrl + 'api/chat/prompt/status/' + jobId))
        .then(response => {
          const chatMessage: ChatMessage = {
            id: uuidv4(),
            sender: 'system',
            text: response.content,
            mappable: response.mappable,
            ambiguous: response.ambiguous,
            purpose: 'standard',
            location: response.location,
            reasoning: response.reasoning
          };
          return chatMessage;
        });
    }
  }

  getLocations(messages: ChatMessage[], offset: number, limit: number): Promise<LocationPage[]> {
    const cacheId = this.explorerSessionState.getOrCreateLocationsRequestId(messages, offset, limit);
    const cachedPages = this.explorerSessionState.getPages(cacheId);

    if (cachedPages) {
      return Promise.resolve(cachedPages);
    }

    if (environment.mockRequests)
    {
      return new Promise<LocationPage[]>((resolve) => {
        setTimeout(() => {
          resolve([MockUtil.locations]);
        }, 500); // Simulating network delay
      }).then(pages => {
        this.explorerSessionState.cachePages(pages, 'chat-mapit', cacheId);
        return pages;
      });
    }
    else
    {
      const params = {
        messages: messages.map(message => ({
          type: message.sender === 'user' ? 'USER' : 'AI',
          content: message.text
        })),
        limit,
        offset
      }

      return firstValueFrom(this.http.post<JobStartResponse>(environment.apiUrl + 'api/chat/get-locations/start', params))
        .then(({ jobId }) => pollJob<LocationPage[]>(this.http, environment.apiUrl + 'api/chat/get-locations/status/' + jobId))
        .then(pages => {
          this.explorerSessionState.cachePages(pages, 'chat-mapit', cacheId);
          return pages;
        });
    }
  }

  getPage(statement: string, type: string | null, offset: number, limit: number, excludedTypes: string[] = [], sortField?: string | null, sortDirection?: 'asc' | 'desc' | null): Promise<LocationPage> {
    const cacheId = this.explorerSessionState.getOrCreatePageRequestId(statement, type, offset, limit, excludedTypes, sortField, sortDirection);
    const cachedPages = this.explorerSessionState.getPages(cacheId);
    const cachedPage = cachedPages?.[0];

    if (cachedPage) {
      return Promise.resolve(cachedPage);
    }

    if (environment.mockRequests)
    {
      return new Promise<LocationPage>((resolve) => {
        setTimeout(() => {
          resolve(MockUtil.locations);
        }, 500); // Simulating network delay
      }).then(page => {
        this.explorerSessionState.cachePages([page], 'page-query', cacheId);
        return page;
      });
    }
    else
    {
      // // // Uncomment below to make a real HTTP request
      const params = {
        statement,
        type,
        limit,
        offset,
        excludedTypes,
        sortField,
        sortDirection
      }

      return firstValueFrom(this.http.post<LocationPage>(environment.apiUrl + 'api/chat/get-page', params))
        .then(page => {
          this.explorerSessionState.cachePages([page], 'page-query', cacheId);
          return page;
      });
    }
  }

  exportPage(statement: string, type: string | null, excludedTypes: string[] = [], sortField?: string | null, sortDirection?: 'asc' | 'desc' | null): Promise<Blob> {
    const params = {
      statement,
      type,
      limit: 0,
      offset: 0,
      excludedTypes,
      sortField,
      sortDirection
    };

    return firstValueFrom(this.http.post(environment.apiUrl + 'api/chat/export-page', params, {
      responseType: 'blob'
    }));
  }

}
