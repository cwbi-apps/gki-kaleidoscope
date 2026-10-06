/**
 * Generates visually distinct random colors by stepping the hue by the golden
 * ratio conjugate. Drop-in replacement for the unmaintained `color-generator`
 * package (which pulled in a ReDoS-vulnerable `color-string`).
 */
const GOLDEN_RATIO_CONJUGATE = 0.618033988749895;
let hue = Math.random();

function hsvToHex(h: number, s: number, v: number): string {
    const i = Math.floor(h * 6);
    const f = h * 6 - i;
    const p = v * (1 - s);
    const q = v * (1 - f * s);
    const t = v * (1 - (1 - f) * s);
    const [r, g, b] = [
        [v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]
    ][i % 6];
    const toHex = (c: number) => Math.round(c * 255).toString(16).padStart(2, '0');
    return '#' + toHex(r) + toHex(g) + toHex(b);
}

export default function ColorGen(saturation = 0.5, value = 0.95): { hexString(): string } {
    hue = (hue + GOLDEN_RATIO_CONJUGATE) % 1;
    const hex = hsvToHex(hue, saturation, value).toUpperCase();
    return { hexString: () => hex };
}
