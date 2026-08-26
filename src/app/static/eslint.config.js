const globals = require("globals");

module.exports = [
    {
        ignores: [
            "unzipit-worker.module.mjs",
            "unzipit.module.mjs",
            "jquery-3.7.1.min.js",
            "mp4box.all.js",
            "*.min.js",
        ],
    },
    {
        files: ["**/*.js", "**/*.mjs"],
        languageOptions: {
            ecmaVersion: 2020,
            sourceType: "module",
            parserOptions: {
                allowImportExportEverywhere: true,
            },
            globals: {
                ...globals.browser,
                ...globals.node,
                API_BASE: "readonly",
                LAMBDA_API_BASE: "readonly",
                MAX_FILE_UPLOAD: "readonly",
                api_key: "readonly",
                demo_mode: "readonly",
                Chart: "readonly",
                upload_movie: "readonly",
                play_clicked: "readonly",
                hide_clicked: "readonly",
                row_pencil_clicked: "readonly",
                action_button_clicked: "readonly",
                planttracer_endpoint: "readonly",
                user_id: "readonly",
                user_default_course_id: "readonly",
                course_choices: "readonly",
                course_view_id: "readonly",
                course_view_name: "readonly",
                super_role: "readonly",
                admin: "readonly",
            },
        },
        rules: {
            "no-unused-vars": [
                "error",
                {
                    args: "all",
                    argsIgnorePattern: "^_",
                    caughtErrors: "all",
                    caughtErrorsIgnorePattern: "^_",
                    destructuredArrayIgnorePattern: "^_",
                    varsIgnorePattern: "^_",
                    ignoreRestSiblings: true,
                },
            ],
        },
    },
];
