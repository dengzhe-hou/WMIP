import { generateProblem } from './generator.mjs';

/** Export exploratory tasks with the core protocol's runner/scorer metadata.
 * Keep the requested seed and probe indices; this is not the frozen bank,
 * which redraws degenerate items and fixes its own published sample.
 */
export function* generateBatchItems(seed, k, count) {
  if (!Number.isInteger(count) || count < 1 || count > 1000) {
    throw new RangeError('Number of tasks must be an integer from 1 to 1000.');
  }
  for (let probeIdx = 0; probeIdx < count; probeIdx++) {
    const problem = generateProblem(seed, k, probeIdx);
    yield {
      source: 'browser-generated',
      item_id: `core-s${seed}-k${k}-p${probeIdx}`,
      block: 'A',
      seed,
      k,
      probe_idx: probeIdx,
      prompt: problem.prompt,
      gold: problem.gold,
      answer_type: 'int',
      max_tokens: 16,
      n_relevant_ops: problem.n_relevant_ops,
      legacy_scoring: 'wmf_am_frozen_v1.parse_answer',
    };
  }
}

export function serializeItem(item) {
  return `${JSON.stringify(item)}\n`;
}
