import { Ratelimit } from '@upstash/ratelimit';
import { Redis } from '@upstash/redis';

// Falls back to an in-memory limiter when no Upstash credentials are present.
let limiter: Ratelimit | null = null;

if (process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN) {
  limiter = new Ratelimit({
    redis: Redis.fromEnv(),
    limiter: Ratelimit.slidingWindow(60, '1 m'),
    prefix: 'h1b-api',
  });
}

const memoryBuckets = new Map<string, { count: number; resetAt: number }>();

function memoryLimit(key: string, max = 60, windowMs = 60_000) {
  const now = Date.now();
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
