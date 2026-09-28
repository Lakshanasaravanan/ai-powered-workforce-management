import tseslint from "typescript-eslint";
export default [{
  files: ["src/**/*.{ts,tsx}"],
  ignores: ["dist/**", "node_modules/**"],
  languageOptions: { ecmaVersion: "latest", sourceType: "module", parser: tseslint.parser },
  rules: {}
}];
