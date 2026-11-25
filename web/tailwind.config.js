/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Segoe UI"', 'system-ui', '-apple-system', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['Consolas', 'ui-monospace', '"Cascadia Mono"', 'Menlo', 'monospace'],
      },
      colors: {
        marca: {
          50: '#effcf9', 100: '#c9f6ec', 200: '#94ecd9', 300: '#57dbc2', 400: '#28c1a8',
          500: '#0fa58f', 600: '#088575', 700: '#0b6a5f', 800: '#0e554d', 900: '#104740', 950: '#022b27',
        },
      },
      boxShadow: { cartao: '0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)' },
    },
  },
  plugins: [],
}
