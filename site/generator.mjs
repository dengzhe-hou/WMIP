// Browser implementation of build_problem and main_prompt from the public release.
// Integer seeding and random draws match Python's random.Random.

const ENTITY_NAMES = [
  'Alice', 'Bob', 'Carol', 'David', 'Emma', 'Frank', 'Grace',
  'Henry', 'Iris', 'James', 'Kate', 'Leo', 'Mia', 'Noah',
];

class PythonRandom {
  constructor(seed) {
    const key = [seed >>> 0];
    if (seed > 0xffffffff) key.push(Math.floor(seed / 0x100000000));
    this.mt = new Uint32Array(624);
    this.mt[0] = 19650218;
    for (let i = 1; i < 624; i++) {
      const previous = this.mt[i - 1];
      this.mt[i] = (Math.imul(previous ^ (previous >>> 30), 1812433253) + i) >>> 0;
    }
    let i = 1;
    let j = 0;
    for (let remaining = Math.max(624, key.length); remaining > 0; remaining--) {
      const previous = this.mt[i - 1];
      this.mt[i] = ((this.mt[i] ^ Math.imul(previous ^ (previous >>> 30), 1664525)) + key[j] + j) >>> 0;
      i++;
      j++;
      if (i >= 624) {
        this.mt[0] = this.mt[623];
        i = 1;
      }
      if (j >= key.length) j = 0;
    }
    for (let remaining = 623; remaining > 0; remaining--) {
      const previous = this.mt[i - 1];
      this.mt[i] = ((this.mt[i] ^ Math.imul(previous ^ (previous >>> 30), 1566083941)) - i) >>> 0;
      i++;
      if (i >= 624) {
        this.mt[0] = this.mt[623];
        i = 1;
      }
    }
    this.mt[0] = 0x80000000;
    this.index = 624;
  }

  nextUint32() {
    if (this.index === 624) {
      for (let i = 0; i < 624; i++) {
        const value = (this.mt[i] & 0x80000000) | (this.mt[(i + 1) % 624] & 0x7fffffff);
        this.mt[i] = this.mt[(i + 397) % 624] ^ (value >>> 1) ^ ((value & 1) ? 0x9908b0df : 0);
      }
      this.index = 0;
    }
    let value = this.mt[this.index++];
    value ^= value >>> 11;
    value ^= (value << 7) & 0x9d2c5680;
    value ^= (value << 15) & 0xefc60000;
    value ^= value >>> 18;
    return value >>> 0;
  }

  below(n) {
    const bits = 32 - Math.clz32(n);
    let value;
    do {
      value = this.nextUint32() >>> (32 - bits);
    } while (value >= n);
    return value;
  }

  randint(low, high) {
    return low + this.below(high - low + 1);
  }

  choice(values) {
    return values[this.below(values.length)];
  }

  sample(values, count) {
    // Both calls in build_problem use Python's small-population pool algorithm.
    const pool = [...values];
    const result = [];
    for (let i = 0; i < count; i++) {
      const j = this.below(values.length - i);
      result.push(pool[j]);
      pool[j] = pool[values.length - i - 1];
    }
    return result;
  }
}

function mainPrompt(initialState, ops, queryEntity) {
  const stateText = Object.entries(initialState).map(([entity, value]) => `${entity}: ${value} points`).join(', ');
  const operationsText = ops.map(([text], index) => `  ${index + 1}. ${text}`).join('\n');
  return 'You will track a sequence of point updates. '
    + 'You cannot refer back to the initial state after reading it once.\n\n'
    + `Initial state:\n${stateText}\n\n`
    + `Operations (apply in order):\n${operationsText}\n\n`
    + `After all operations, how many points does ${queryEntity} have?\n\n`
    + 'Respond with ONLY the final number.';
}

/** Generate a main-probe task. k is 1–1000; seed is an unsigned 32-bit integer. */
export function generateProblem(seed, k, probeIdx = 0) {
  if (!Number.isInteger(seed) || seed < 0 || seed > 0xffffffff) {
    throw new RangeError('Seed must be an integer from 0 to 4294967295.');
  }
  if (!Number.isInteger(k) || k < 1 || k > 1000) {
    throw new RangeError('Sequence length must be an integer from 1 to 1000.');
  }
  const combinedSeed = seed + k * 1000 + probeIdx;
  if (!Number.isSafeInteger(probeIdx) || probeIdx < 0 || !Number.isSafeInteger(combinedSeed)) {
    throw new RangeError('Probe index and combined seed must be nonnegative safe integers.');
  }
  const rng = new PythonRandom(combinedSeed);
  const entities = rng.sample(ENTITY_NAMES, 3);
  const state = Object.fromEntries(entities.map(entity => [entity, rng.randint(5, 20)]));
  const initialState = { ...state };
  const states = [{ ...state }];
  const ops = [];

  for (let step = 0; step < k; step++) {
    const opType = rng.choice(['add', 'subtract', 'transfer']);
    if (opType === 'add') {
      const entity = rng.choice(entities);
      const amount = rng.randint(1, 10);
      state[entity] += amount;
      ops.push([`${entity} gains ${amount} points.`, [entity], 'gain']);
    } else if (opType === 'subtract') {
      const entity = rng.choice(entities);
      const amount = Math.min(rng.randint(1, 5), state[entity] - 1);
      if (amount > 0) {
        state[entity] -= amount;
        ops.push([`${entity} loses ${amount} points.`, [entity], 'lose']);
      } else {
        state[entity] += 1;
        ops.push([`${entity} gains 1 point.`, [entity], 'gain_one']);
      }
    } else {
      const [giver, receiver] = rng.sample(entities, 2);
      const amount = Math.min(rng.randint(1, 3), state[giver] - 1);
      if (amount > 0) {
        state[giver] -= amount;
        state[receiver] += amount;
        ops.push([`${giver} gives ${amount} points to ${receiver}.`, [giver, receiver], 'transfer']);
      } else {
        ops.push(['No transfer occurs this round.', [], 'no_transfer']);
      }
    }
    states.push({ ...state });
  }

  const queryEntity = rng.choice(entities);
  return {
    seed,
    k,
    probe_idx: probeIdx,
    initial_state: initialState,
    ops,
    query_entity: queryEntity,
    gold: state[queryEntity],
    n_relevant_ops: ops.filter(([, changed]) => changed.includes(queryEntity)).length,
    prompt: mainPrompt(initialState, ops, queryEntity),
    states,
  };
}
