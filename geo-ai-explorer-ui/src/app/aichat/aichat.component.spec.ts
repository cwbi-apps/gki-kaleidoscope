import { ComponentFixture, TestBed } from '@angular/core/testing';

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
});
