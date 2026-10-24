/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1c1917",
        paper: "#f3efe6",
        card: "#fffdf8",
        line: "#e4dccd",
        pine: {
          50: "#f2f8f6",
          100: "#dceee8",
          600: "#0f6e62",
          700: "#0c574e",
          800: "#0a433c",
        },
        clay: "#9a3412",
      },
      fontFamily: {
        sans: ["Source Sans 3", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Outfit", "Source Sans 3", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(28, 25, 23, 0.04), 0 12px 32px rgba(28, 25, 23, 0.04)",
      },
    },
  },
  plugins: [],
}
