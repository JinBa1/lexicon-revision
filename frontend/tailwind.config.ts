import type { Config } from "tailwindcss";
import { archiveTokens } from "./src/theme/tokens";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: archiveTokens.colors,
      fontFamily: archiveTokens.fontFamily,
      borderRadius: archiveTokens.borderRadius,
      boxShadow: archiveTokens.boxShadow,
    },
  },
  plugins: [],
} satisfies Config;
