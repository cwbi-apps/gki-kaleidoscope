/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { MessageService } from 'primeng/api';

import { ErrorService } from './error-service.service';

describe('ErrorService', () => {
  let service: ErrorService;
  let messageService: jasmine.SpyObj<MessageService>;

  beforeEach(() => {
    messageService = jasmine.createSpyObj<MessageService>('MessageService', ['add']);

    TestBed.configureTestingModule({
      providers: [{ provide: MessageService, useValue: messageService }]
    });

    service = TestBed.inject(ErrorService);
  });

  it('reports a 401 as an expired session, once', () => {
    service.handleError(new HttpErrorResponse({ status: 401 }));
    service.handleError(new HttpErrorResponse({ status: 401 }));

    expect(messageService.add).toHaveBeenCalledTimes(1);
    expect(messageService.add.calls.mostRecent().args[0]).toEqual(jasmine.objectContaining({ key: 'session', summary: 'Session expired' }));
  });

  it('reports a 403 as a blocked request, not an expired session', () => {
    service.handleError(new HttpErrorResponse({ status: 403 }));

    expect(messageService.add).toHaveBeenCalledTimes(1);
    expect(messageService.add.calls.mostRecent().args[0]).toEqual(jasmine.objectContaining({ key: 'explorer', summary: 'Request blocked' }));
  });
});
