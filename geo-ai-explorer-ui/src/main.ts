import { provideZoneChangeDetection } from "@angular/core";
import { bootstrapApplication } from '@angular/platform-browser';
import { setWorkerUrl } from 'maplibre-gl';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';

// MapLibre 6 loads its web worker from a separate file next to its own module
// (new URL('./maplibre-gl-worker.mjs', import.meta.url)). Angular's bundler moves
// maplibre-gl, so that file isn't found. angular.json copies the worker (and the
// shared chunk it imports) into /maplibre; point MapLibre at it. Resolved against
// <base href> so it also works under a context path such as /kaleidoscope/.
setWorkerUrl(new URL('maplibre/maplibre-gl-worker.mjs', document.baseURI).href);

bootstrapApplication(AppComponent, {...appConfig, providers: [provideZoneChangeDetection(), ...appConfig.providers]})
  .catch((err) => console.error(err));
