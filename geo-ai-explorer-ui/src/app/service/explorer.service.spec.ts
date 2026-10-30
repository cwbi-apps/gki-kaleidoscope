/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { TestBed } from '@angular/core/testing';

import { ExplorerService as ExplorerService } from './explorer.service';

describe('GraphQueryService', () => {
  let service: ExplorerService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ExplorerService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
