import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { v4 as uuidv4 } from 'uuid';

import { ChatMessage, LocationPage } from '../models/chat.model';

export type CachedExplorerPagesSource =
  | 'chat-mapit'
  | 'full-text-disambiguation'
  | 'page-query'
  | 'unknown';

export interface CachedExplorerPages {
  id: string;
  createdAt: number;
  updatedAt: number;
  pages: LocationPage[];
  source: CachedExplorerPagesSource;
  title: string;
  saved: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ExplorerSessionStateService {
  private readonly prefix = 'explorer.pages.';
  private readonly savedPrefix = 'explorer.savedPages.';

  private readonly queryHistorySubject = new BehaviorSubject<CachedExplorerPages[]>(this.listCachedPages());

  readonly queryHistory$ = this.queryHistorySubject.asObservable();

  cachePages(pages: LocationPage[], source: CachedExplorerPagesSource = 'unknown', id: string = uuidv4(), title?: string): string {
    if (!this.hasResults(pages)) {
      this.deleteCachedPages(id);
      return id;
    }

    const existing = this.getCache(id);
    const saved = existing?.saved ?? this.hasSavedCache(id);

    const cache: CachedExplorerPages = {
      id,
      createdAt: existing?.createdAt ?? Date.now(),
      updatedAt: Date.now(),
      pages,
      source: source === 'unknown'
        ? existing?.source ?? source
        : source,
      title: title ?? existing?.title ?? this.buildTitle(pages, source),
      saved
    };

    try {
      sessionStorage.setItem(this.storageKey(id), JSON.stringify(cache));

      if (saved) {
        localStorage.setItem(this.savedStorageKey(id), JSON.stringify(cache));
      }

      this.refreshQueryHistory();
    } catch (error) {
      console.warn('Failed to cache explorer pages in sessionStorage', error);
    }

    return id;
  }

  hasResults(pages: LocationPage[] | null | undefined): boolean {
    return (pages ?? []).some(page =>
      (page.count ?? 0) > 0 ||
      (page.locations?.length ?? 0) > 0
    );
  }

  getPages(id: string | null | undefined): LocationPage[] | null {
    if (!id) {
      return null;
    }

    try {
      const cache = this.getCache(id);

      if (!cache) {
        return null;
      }

      return Array.isArray(cache.pages)
        ? cache.pages
        : null;
    } catch (error) {
      console.warn('Failed to read cached explorer pages from sessionStorage', error);
      return null;
    }
  }

  getOrCreatePageRequestId(statement: string, type: string, offset: number, limit: number): string {
    return [
      'page-query',
      this.hash(statement),
      this.hash(type),
      offset,
      limit
    ].join('.');
  }

  getOrCreateLocationsRequestId(messages: ChatMessage[], offset: number, limit: number): string {
    const key = JSON.stringify({
      messages: messages.map(message => ({
        sender: message.sender,
        text: message.text,
        purpose: message.purpose
      })),
      offset,
      limit
    });

    return ['locations-query', this.hash(key)].join('.');
  }

  getOrCreateFullTextLookupId(query: string): string {
    return ['full-text', this.hash(query)].join('.');
  }

  listCachedPages(): CachedExplorerPages[] {
    const caches = new Map<string, CachedExplorerPages>();

    this.collectCaches(sessionStorage, this.prefix).forEach(cache => {
      caches.set(cache.id, cache);
    });

    this.collectCaches(localStorage, this.savedPrefix).forEach(cache => {
      const existing = caches.get(cache.id);

      caches.set(cache.id, {
        ...cache,
        ...existing,
        saved: true
      });
    });

    return Array.from(caches.values())
      .sort((a, b) => b.updatedAt - a.updatedAt);
  }

  saveCachedPages(id: string): void {
    const cache = this.getCache(id);

    if (!cache) {
      return;
    }

    const savedCache: CachedExplorerPages = {
      ...cache,
      saved: true,
      updatedAt: Date.now()
    };

    try {
      sessionStorage.setItem(this.storageKey(id), JSON.stringify(savedCache));
      localStorage.setItem(this.savedStorageKey(id), JSON.stringify(savedCache));
      this.refreshQueryHistory();
    } catch (error) {
      console.warn('Failed to save explorer pages cache', error);
    }
  }

  unsaveCachedPages(id: string): void {
    const cache = this.getCache(id);

    if (!cache) {
      return;
    }

    const unsavedCache: CachedExplorerPages = {
      ...cache,
      saved: false,
      updatedAt: Date.now()
    };

    try {
      localStorage.removeItem(this.savedStorageKey(id));
      sessionStorage.setItem(this.storageKey(id), JSON.stringify(unsavedCache));
      this.refreshQueryHistory();
    } catch (error) {
      console.warn('Failed to unsave explorer pages cache', error);
    }
  }

  deleteCachedPages(id: string): void {
    try {
      sessionStorage.removeItem(this.storageKey(id));
      localStorage.removeItem(this.savedStorageKey(id));
      this.refreshQueryHistory();
    } catch (error) {
      console.warn('Failed to delete explorer pages cache', error);
    }
  }

  private getCache(id: string | null | undefined): CachedExplorerPages | null {
    if (!id) {
      return null;
    }

    const sessionCache = this.readCache(sessionStorage, this.storageKey(id));

    if (sessionCache) {
      return {
        ...sessionCache,
        saved: sessionCache.saved || this.hasSavedCache(id)
      };
    }

    const savedCache = this.readCache(localStorage, this.savedStorageKey(id));

    if (savedCache) {
      const restored = {
        ...savedCache,
        saved: true
      };

      try {
        sessionStorage.setItem(this.storageKey(id), JSON.stringify(restored));
      } catch (error) {
        console.warn('Failed to restore saved explorer pages cache into sessionStorage', error);
      }

      return restored;
    }

    return null;
  }

  private hasSavedCache(id: string): boolean {
    return localStorage.getItem(this.savedStorageKey(id)) != null;
  }

  private collectCaches(storage: Storage, prefix: string): CachedExplorerPages[] {
    const caches: CachedExplorerPages[] = [];

    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);

      if (!key?.startsWith(prefix)) {
        continue;
      }

      const cache = this.readCache(storage, key);

      if (cache) {
        caches.push(cache);
      }
    }

    return caches;
  }

  private readCache(storage: Storage, key: string): CachedExplorerPages | null {
    const raw = storage.getItem(key);

    if (!raw) {
      return null;
    }

    try {
      const cache = JSON.parse(raw) as CachedExplorerPages;

      if (!cache?.id || !Array.isArray(cache.pages)) {
        return null;
      }

      return {
        ...cache,
        createdAt: cache.createdAt ?? Date.now(),
        updatedAt: cache.updatedAt ?? cache.createdAt ?? Date.now(),
        title: cache.title ?? this.buildTitle(cache.pages, cache.source ?? 'unknown'),
        saved: cache.saved ?? false
      };
    } catch (error) {
      console.warn('Failed to parse cached explorer pages', error);
      return null;
    }
  }

  private refreshQueryHistory(): void {
    this.queryHistorySubject.next(this.listCachedPages());
  }

  private storageKey(id: string): string {
    return `${this.prefix}${id}`;
  }

  private savedStorageKey(id: string): string {
    return `${this.savedPrefix}${id}`;
  }

  private buildTitle(pages: LocationPage[], source: CachedExplorerPagesSource): string {
    const total = pages.reduce((sum, page) => sum + (page.count ?? page.locations?.length ?? 0), 0);
    const typeLabels = pages
      .map(page => this.typeLabel(page.type))
      .filter(label => label.length > 0);
    const uniqueTypeLabels = Array.from(new Set(typeLabels));
    const label = uniqueTypeLabels.length > 0
      ? uniqueTypeLabels.slice(0, 2).join(', ')
      : this.sourceLabel(source);

    return total > 0
      ? `${label} (${total})`
      : label;
  }

  private typeLabel(type: string | null | undefined): string {
    if (!type?.trim()) {
      return '';
    }

    const hashIndex = type.lastIndexOf('#');
    const slashIndex = type.lastIndexOf('/');
    const index = Math.max(hashIndex, slashIndex);

    return index === -1
      ? type
      : type.substring(index + 1);
  }

  private sourceLabel(source: CachedExplorerPagesSource): string {
    if (source === 'chat-mapit') return 'Mapped chat query';
    if (source === 'full-text-disambiguation') return 'Disambiguation query';
    if (source === 'page-query') return 'Page query';

    return 'Cached query';
  }

  private hash(value: string): string {
    let hash = 0;

    for (let i = 0; i < value.length; i++) {
      hash = ((hash << 5) - hash) + value.charCodeAt(i);
      hash |= 0;
    }

    return Math.abs(hash).toString(36);
  }
}
