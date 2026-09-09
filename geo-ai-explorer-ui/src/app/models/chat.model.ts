import { GeoObject } from "./geoobject.model";

export interface MessageSection {
  text: string;
  type: number;
  uri?: string;
}


export interface ChatMessage {
  id: string
  sender: 'user' | 'system';
  text: string;
  mappable: boolean;
  ambiguous?: boolean;
  location?: string;
  sections?: MessageSection[];
  loading?: boolean;
  purpose: 'info' | 'standard'
}

export interface ServerChatResponse {
  content: string;
  sessionId: string;
  mappable: boolean;
  ambiguous: boolean;
  conversationTitle?: string;
  location?: string;
}

export interface TypeSummary {
  type: string;
  count: number;
}

export interface LocationPage {
  statement: string;
  type: string | null,
  locations: GeoObject[];
  limit: number;
  offset: number;
  count: number;
  sortField?: string | null;
  sortDirection?: 'asc' | 'desc' | null;
  availableTypes?: TypeSummary[];
}

/**
 * Returned immediately by the /api/chat/prompt/start and
 * /api/chat/get-locations/start endpoints. The actual response is fetched
 * by polling JobStatusResponse via the returned jobId.
 */
export interface JobStartResponse {
  jobId: string;
}

/**
 * Polled from /api/chat/prompt/status/{jobId} and
 * /api/chat/get-locations/status/{jobId} until status is SUCCEEDED or
 * FAILED. `result` is only populated once SUCCEEDED.
 */
export interface JobStatusResponse<T> {
  jobId: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  result?: T;
  errorMessage?: string;
}
