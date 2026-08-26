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
            "@html-eslint/indent": "off",
            "@html-eslint/quotes": "off",
            "@html-eslint/attrs-newline": "off",
            "@html-eslint/element-newline": "off",
            "@html-eslint/no-extra-spacing-attrs": "off",
            "@html-eslint/no-extra-spacing-tags": "off",
            "@html-eslint/no-obsolete-attrs": "off",
            "@html-eslint/use-baseline": "off",
        },
    },
];
