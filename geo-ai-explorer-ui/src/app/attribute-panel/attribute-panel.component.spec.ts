/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AttributePanelComponent } from './attribute-panel.component';
import { provideTestApp } from '../testing/test-providers';

describe('AttributePanelComponent', () => {
  let component: AttributePanelComponent;
  let fixture: ComponentFixture<AttributePanelComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AttributePanelComponent],
      providers: provideTestApp()
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(AttributePanelComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
