/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
// Local development against an API deployed under a servlet context path.
// Used by `npm run start:context` (angular.json "development-context"), which
// serves the UI at http://localhost:4200/kaleidoscope/. Run the API with
// `-Dapp.context=/kaleidoscope` (cargo-run profile) to match.
export const environment = {
    production: false,
    apiUrl: 'http://localhost:8080/kaleidoscope/',
    basePrefix: 'https://localhost:4200',
    mockRequests: false
  };
