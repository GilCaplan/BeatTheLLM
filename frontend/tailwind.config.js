/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'hacker-green': '#00ff41',
        'hacker-dark': '#0d0d0d',
        'hacker-gray': '#1a1a2e',
        'hacker-blue': '#16213e',
        'hacker-accent': '#0f3460',
        'hacker-red': '#e94560',
        'hacker-yellow': '#f5a623',
      },
      fontFamily: {
        mono: ['"Fira Code"', '"Cascadia Code"', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-green': 'pulse-green 2s infinite',
        'glitch': 'glitch 0.3s infinite',
        'scanline': 'scanline 8s linear infinite',
        'blink': 'blink 1s step-end infinite',
      },
      keyframes: {
        'pulse-green': {
          '0%, 100%': { textShadow: '0 0 5px #00ff41, 0 0 10px #00ff41' },
          '50%': { textShadow: '0 0 20px #00ff41, 0 0 40px #00ff41, 0 0 80px #00ff41' },
        },
        'glitch': {
          '0%': { transform: 'translate(0)' },
          '33%': { transform: 'translate(-2px, 1px)' },
          '66%': { transform: 'translate(2px, -1px)' },
          '100%': { transform: 'translate(0)' },
        },
        'scanline': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        'blink': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
    },
  },
  plugins: [],
}
