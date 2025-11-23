const html = require("@html-eslint/eslint-plugin");
const parser = require("@html-eslint/parser");

module.exports = [
    // recommended configuration included in the plugin
    html.configs["flat/recommended"],
    // your own configurations.
    {
        files: ["**/*.html"],
        plugins: {
            "@html-eslint": html,
        },
        languageOptions: {
            parser,
        },
        rules: {
            "@html-eslint/indent": "error",
            "@html-eslint/quotes": "off",
            "@html-eslint/element-newline": "off",
            "@html-eslint/indent": "off",
            "@html-eslint/no-extra-spacing-attrs": "off",
        },
    },
];
