import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#f4f1ea',
        ink: {
          DEFAULT: '#111111',
          50: '#f7f5ef',
          100: '#eceae2',
          200: '#d8d5cc',
          300: '#bab6ac',
          400: '#8a867c',
          500: '#5e5b52',
          600: '#3b3a35',
          700: '#252421',
          800: '#18181a',
          900: '#111111',
        },
        accent: '#9a1f1f',
        critical: '#9a1f1f',
        high: '#a0661f',
        medium: '#7a6b1f',
        low: '#4c6b3d',
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['var(--font-serif)', 'ui-serif', 'Georgia', 'serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
