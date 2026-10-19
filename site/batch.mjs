import { generateProblem } from './generator.mjs';

/** Keep one seed and advance the probe index for each requested task. */
export function* generateBatchItems(seed, k, count) {
  if (!Number.isInteger(count) || count < 1 || count > 1000) {
    throw new RangeError('Number of tasks must be an integer from 1 to 1000.');
  }
  for (let probeIdx = 0; probeIdx < count; probeIdx++) {
    const problem = generateProblem(seed, k, probeIdx);
    yield {
      source: 'browser-generated',
      item_id: `core-s${seed}-k${k}-p${probeIdx}`,
      seed,
      k,
      probe_idx: probeIdx,
      prompt: problem.prompt,
      gold: problem.gold,
      answer_type: 'int',
    };
  }
}

export function serializeItem(item) {
  return `${JSON.stringify(item)}\n`;
}
