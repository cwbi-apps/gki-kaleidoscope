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
