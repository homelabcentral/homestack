# Roadmap

## ✅ Completed Features

### 2. Variable Derivation (derive=)
Environment variables can now derive values from other variables using `${VAR}` syntax. The `derive=` metadata field in `.env.template` enables building composite values from shared configuration with 3-layer precedence: `00.env/*.env` < current `.env` < in-session answers. Immutable variables auto-apply derived values; mutable variables show them as recommended defaults.

- **Implementation**: `utils/text_interpolation.py` + parser support in `parsers/env_template_parser.py`
- **Form builder**: `cli/questionary.py` with full validation (type, choices, secret rejection)
- **Testing**: 145+ test cases covering derive, compute, and mixed scenarios
- **Documentation**: Updated README with syntax, examples, and precedence rules

### 4. Rich Console Formatting (User-Facing Messages)
New `utils/rich_formatter.py` module provides beautifully formatted console messages via a global singleton. 10 message types (info, error, warning, debug, success, hint, step, command, result, title) with contextual emoji, colors, and formatting. Helper methods for panels, tables, code blocks, and specialized formatters for common CLI patterns.

- **Implementation**: `src/utils/rich_formatter.py` (388 lines) + global singleton
- **Features**: 10 message types + helper methods + specialized formatters
- **Testing**: 113 comprehensive test cases
- **Demo**: `scripts/demo_rich_formatter.py` showcasing all features
- **Ready for integration** into cli.py commands (gradual migration path provided)

### 9. Loading All Env Into Memory
Shared environment files from `00.env/*.env` are now loaded into memory during template generation and deployment. The `load_interpolation_context()` function builds a unified resolution context from shared files + current project .env + in-session answers, enabling efficient variable interpolation and derivation across the entire stack.

- **Implementation**: `utils/text_interpolation.py`
- **CLI integration**: Both deploy and init/update commands load and pass interpolation context
- **Precedence**: Documented and tested with comprehensive coverage

---

## 🚀 In Progress / Planned Features

## 1. Pre-install steps

While deploying, if there are any pre-install steps in projects.json then ask user if they have completed the steps and only if the answer is yes for all then deploy the stack. eg. execute the deploy command.

## 3. Add DNS entry automatically to pihole

Add dns entry automatically to the local pihole instance using pihole python api, on failure warn user and let them know to add the entry manually.

## 5. Add a command to view secrets for a project

Add a new command to display secrets (only the ones user needs to save/remember with an option to show all) for a project

## 6. Add the password for a particular service to vaultwarden

Add the username, password automatically using python commands to the local vaultwarden

## 7. Add extends capabilities for .yml

Add common .yml files into `00.common` what can be extended into a `docker-compose.yml` file with questionary. for example, add nvidia block of code. Example already setup - immich. Control the flow using .env.template

## 8. Depends on tag

## 10. Resolving variables from json, readme and env
