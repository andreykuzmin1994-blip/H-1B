import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        critical: '#b91c1c',
        high: '#ea580c',
        medium: '#f59e0b',
        low: '#84cc16',
      },
    },
  },
  plugins: [],
};

export default config;
