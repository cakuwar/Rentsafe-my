// ESLint 9 flat config: `npm run lint`. ESLint's recommended rules for
// Node ES modules; tests and scripts are linted too.
import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      globals: { ...globals.node },
    },
    rules: {
      // A leading underscore marks a value dropped on purpose: a parameter kept
      // for its position, or a field left out by destructuring ({ id: _id, ...rest }).
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", ignoreRestSiblings: true }],
    },
  },
  {
    files: ["tests/**/*.js"],
    // vitest's describe/it/expect are imported explicitly; fetch, Response and
    // AbortSignal are Node 18+ globals.
    languageOptions: { globals: { ...globals.node } },
  },
  { ignores: ["node_modules/**", "coverage/**"] },
];
