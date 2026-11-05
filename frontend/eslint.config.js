// ESLint 9 flat config: `npm run lint`. ESLint's recommended rules for the
// browser, with JSX parsed. Without eslint-plugin-react, a component used only
// in JSX looks unused to ESLint, so capitalised names are exempt.
import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser },
    },
    rules: {
      "no-unused-vars": ["error", { varsIgnorePattern: "^[A-Z_]", argsIgnorePattern: "^_", ignoreRestSiblings: true }],
    },
  },
  { ignores: ["dist/**", "node_modules/**"] },
];
