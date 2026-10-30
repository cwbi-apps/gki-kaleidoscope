/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Meta } from '@angular/platform-browser';

import { AichatComponent } from './aichat.component';
import { provideTestApp } from '../testing/test-providers';

describe('AichatComponent', () => {
  let component: AichatComponent;
  let fixture: ComponentFixture<AichatComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AichatComponent],
      providers: provideTestApp()
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(AichatComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should hide the version when the server did not render one', () => {
    expect(component.appVersion).toBeNull();
    expect(fixture.nativeElement.querySelector('.sidebar-version')).toBeNull();
  });

  it('should show the version rendered into index.html by the server', () => {
    const meta = TestBed.inject(Meta);
    meta.addTag({ name: 'app-version', content: '1.2.3', 'data-build-time': '2026-10-28T23:00:11Z' });

    try {
      const versionFixture = TestBed.createComponent(AichatComponent);
      versionFixture.detectChanges();

      const element: HTMLElement = versionFixture.nativeElement.querySelector('.sidebar-version');
      expect(element.textContent?.trim()).toBe('v1.2.3');
      expect(element.title).toContain('Built ');
    } finally {
      meta.removeTag('name="app-version"');
    }
  });
});
