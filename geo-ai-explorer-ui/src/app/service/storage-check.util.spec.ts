/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { checkLocalStorage } from './storage-check.util';

describe('checkLocalStorage', () => {
  it('passes when localStorage works', () => {
    expect(checkLocalStorage()).toEqual({ ok: true, details: [] });
  });

  it('fails with the error when writing throws', () => {
    spyOn(Storage.prototype, 'setItem').and.callFake(() => {
      throw new DOMException('The quota has been exceeded.', 'QuotaExceededError');
    });

    const result = checkLocalStorage();

    expect(result.ok).toBeFalse();
    expect(result.details[0]).toBe('localStorage error: QuotaExceededError: The quota has been exceeded.');
  });

  it('fails when the value is not read back', () => {
    spyOn(Storage.prototype, 'getItem').and.returnValue(null);

    const result = checkLocalStorage();

    expect(result.ok).toBeFalse();
    expect(result.details[0]).toContain('did not match');
  });
});
