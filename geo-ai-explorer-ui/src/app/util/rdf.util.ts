/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
export const GEO = "http://www.opengis.net/ont/geosparql#";

export const GEO_FEATURE = GEO + "Feature";

export const GEO_WKT_LITERAL = GEO + "wktLiteral";

export function uriToLabel(uri: string): string {
    let i = uri.lastIndexOf("#");
    if (i == -1) return uri;

    return uri.substring(i + 1);
}
