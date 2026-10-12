// Synthetic diagnostic envelope. Never read real logs or call an external service.
export function makeDiagnostic(c) {
  if (!c || !Number.isInteger(c.noise_records) || c.noise_records < 1 || c.noise_records > 10000 ||
      !Number.isInteger(c.image_chars) || c.image_chars < 0 || c.image_chars > 100000 ||
      !Number.isInteger(c.exit_code) || typeof c.locator !== 'string' ||
      !(c.failure === null || typeof c.failure === 'string')) throw new Error('invalid fixture');
  return { records: Array.from({ length: c.noise_records }, (_, i) => `irrelevant diagnostic record ${i}`),
    exit_code: c.exit_code, failure: c.failure, locator: c.locator,
    image: c.image_chars ? { type: 'image', data: 'x'.repeat(c.image_chars) } : null };
}

export const policies = {
  full: d => JSON.stringify(d),
  blind_cap: d => JSON.stringify(d).slice(0, 4096),
  focused: d => JSON.stringify({ exit_code: d.exit_code, failure: d.failure, locator: d.locator,
    omitted_records: d.records.length, image_present: d.image !== null })
};

export function quality(output, expected) {
  try {
    const value = JSON.parse(output);
    return value.exit_code === expected.exit_code && value.failure === expected.failure &&
      value.locator === expected.locator;
  } catch { return false; }
}
