import { ComponentFixture, TestBed } from '@angular/core/testing';

import { GraphExplorerComponent } from './graph-explorer.component';
import { provideTestApp } from '../testing/test-providers';

describe('GraphExplorerComponent', () => {
  let component: GraphExplorerComponent;
  let fixture: ComponentFixture<GraphExplorerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [GraphExplorerComponent],
      providers: provideTestApp()
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(GraphExplorerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
