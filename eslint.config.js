/** @type {import("eslint").Linter.Config} */
export default [
  {
    ignores: ["dist/", "node_modules/"],
  },
  {
    files: ["packages/*/src/**/*.ts"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        console: "readonly",
        process: "readonly",
        __dirname: "readonly",
        __filename: "readonly",
      },
    },
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "off",
      "no-console": "off",
    },
  },
];
