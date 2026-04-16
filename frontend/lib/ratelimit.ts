import { Ratelimit } from '@upstash/ratelimit';
import { Redis } from '@upstash/redis';

const RATE_MAX = Number(process.env.RATELIMIT_MAX ?? '60');
const RATE_WINDOW = (process.env.RATELIMIT_WINDOW ?? '1 m') as `${number} ${'s' | 'm' | 'h' | 'd'}`;
const WINDOW_MS = parseWindowMs(RATE_WINDOW);
const MEMORY_MAX_KEYS = 10_000;

function parseWindowMs(win: string): number {
  const [n, unit] = win.trim().split(/\s+/);
  const num = Number(n);
  const mult = unit === 's' ? 1_000 : unit === 'm' ? 60_000 : unit === 'h' ? 3_600_000 : 86_400_000;
  return num * mult;
}

let limiter: Ratelimit | null = null;

if (process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN) {
  limiter = new Ratelimit({
    redis: Redis.fromEnv(),
    limiter: Ratelimit.slidingWindow(RATE_MAX, RATE_WINDOW),
    prefix: 'h1b-api',
  });
}

const memoryBuckets = new Map<string, { count: number; resetAt: number }>();

function memoryLimit(key: string, max = RATE_MAX, windowMs = WINDOW_MS) {
  const now = Date.now();

  if (memoryBuckets.size >= MEMORY_MAX_KEYS) {
    for (const [k, v] of memoryBuckets) {
      if (v.resetAt < now) memoryBuckets.delete(k);
    }
    while (memoryBuckets.size >= MEMORY_MAX_KEYS) {
      const firstKey = memoryBuckets.keys().next().value as string | undefined;
      if (firstKey === undefined) break;
      memoryBuckets.delete(firstKey);
    }
  }

  const current = memoryBuckets.get(key);
  if (!current || now > current.resetAt) {
    memoryBuckets.set(key, { count: 1, resetAt: now + windowMs });
    return { success: true, remaining: max - 1 };
  }
  current.count += 1;
  return { success: current.count <= max, remaining: Math.max(0, max - current.count) };
}

export async function checkRateLimit(key: string) {
  if (limiter) {
    return limiter.limit(key);
  }
  return memoryLimit(key);
}
