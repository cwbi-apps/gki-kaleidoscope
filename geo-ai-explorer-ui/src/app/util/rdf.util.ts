export const GEO = "http://www.opengis.net/ont/geosparql#";

export const GEO_FEATURE = GEO + "Feature";

export const GEO_WKT_LITERAL = GEO + "wktLiteral";

export function uriToLabel(uri: string): string {
    let i = uri.lastIndexOf("#");
    if (i == -1) return uri;

    return uri.substring(i + 1);
}
