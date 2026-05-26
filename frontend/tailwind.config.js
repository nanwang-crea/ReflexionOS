/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
          code: 'var(--bg-code)',
        },
        content: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        edge: {
          DEFAULT: 'var(--border)',
          subtle: 'var(--border-subtle)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          soft: 'var(--accent-soft)',
        },
        terminal: {
          bg: 'var(--terminal-bg)',
          tabbar: 'var(--terminal-tabbar)',
          'tab-active': 'var(--terminal-tab-active)',
        },
        status: {
          error: 'var(--status-error)',
          'error-soft': 'var(--status-error-soft)',
          'error-border': 'var(--status-error-border)',
          warning: 'var(--status-warning)',
          'warning-soft': 'var(--status-warning-soft)',
          'warning-border': 'var(--status-warning-border)',
          success: 'var(--status-success)',
          'success-soft': 'var(--status-success-soft)',
          'success-border': 'var(--status-success-border)',
        },
      },
      boxShadow: {
        theme: '0 8px 30px var(--shadow-color)',
      },
    },
  },
  plugins: [],
}
