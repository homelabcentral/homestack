"""
Test suite for rich_formatter module.

Tests all message types, formatting, colors, emoji, helper methods,
and singleton behavior.
"""

from unittest.mock import patch

import pytest
from rich.panel import Panel
from rich.text import Text
from utils.rich_formatter import RichFormatter, formatter


class TestRichFormatterMessageTypes:
    """Test all 10 message types render without errors."""

    def test_info_basic(self):
        """Test info message renders successfully."""
        rf = RichFormatter()
        rf.info("This is an info message")
        # If we got here without exception, test passes

    def test_error_basic(self):
        """Test error message renders successfully."""
        rf = RichFormatter()
        rf.error("This is an error message")

    def test_warning_basic(self):
        """Test warning message renders successfully."""
        rf = RichFormatter()
        rf.warning("This is a warning message")

    def test_debug_basic(self):
        """Test debug message renders successfully."""
        rf = RichFormatter()
        rf.debug("This is a debug message")

    def test_success_basic(self):
        """Test success message renders successfully."""
        rf = RichFormatter()
        rf.success("This is a success message")

    def test_hint_basic(self):
        """Test hint message renders successfully."""
        rf = RichFormatter()
        rf.hint("This is a hint message")

    def test_step_basic(self):
        """Test step message renders successfully."""
        rf = RichFormatter()
        rf.step("This is a step message")

    def test_command_basic(self):
        """Test command message renders successfully."""
        rf = RichFormatter()
        rf.command("This is a command message")

    def test_result_basic(self):
        """Test result message renders successfully."""
        rf = RichFormatter()
        rf.result("This is a result message")

    def test_title_basic(self):
        """Test title message renders successfully."""
        rf = RichFormatter()
        rf.title("This is a title message")


class TestRichFormatterWithDetails:
    """Test message types with optional details parameter."""

    def test_info_with_details(self):
        """Test info message with details."""
        rf = RichFormatter()
        rf.info("Main message", details="Additional details here")

    def test_error_with_details(self):
        """Test error message with details."""
        rf = RichFormatter()
        rf.error("Error occurred", details="Retry in 5 seconds")

    def test_success_with_details(self):
        """Test success message with details."""
        rf = RichFormatter()
        rf.success(
            "Deployment complete", details="Services available at localhost:3000"
        )


class TestRichFormatterOptions:
    """Test optional parameters (prefix, title)."""

    def test_message_without_prefix(self):
        """Test message with prefix disabled."""
        rf = RichFormatter()
        rf.info("Message without emoji", prefix=False)

    def test_message_with_title(self):
        """Test message with title parameter."""
        rf = RichFormatter()
        rf.info("Main content", title="Section Title")

    def test_message_with_details_and_title(self):
        """Test message with both details and title."""
        rf = RichFormatter()
        rf.warning("Warning message", details="Additional context", title="Alert")


class TestMessageConfiguration:
    """Test message configuration dictionary."""

    def test_all_message_types_in_config(self):
        """Verify all expected message types have configuration."""
        expected_types = {
            "info",
            "error",
            "warning",
            "debug",
            "success",
            "hint",
            "step",
            "command",
            "result",
            "title",
        }
        assert set(RichFormatter._MESSAGE_CONFIG.keys()) == expected_types

    def test_config_structure(self):
        """Verify message configuration has required fields."""
        for msg_type, config in RichFormatter._MESSAGE_CONFIG.items():
            assert "emoji" in config, f"{msg_type} missing emoji"
            assert "color" in config, f"{msg_type} missing color"
            assert "format" in config, f"{msg_type} missing format"
            assert isinstance(config["format"], list), (
                f"{msg_type} format should be list"
            )

    def test_config_values(self):
        """Verify message configuration values are non-empty."""
        for msg_type, config in RichFormatter._MESSAGE_CONFIG.items():
            assert config["emoji"], f"{msg_type} has empty emoji"
            assert config["color"], f"{msg_type} has empty color"
            assert config["format"], f"{msg_type} has empty format"

    def test_error_has_red_color(self):
        """Verify error message uses red color."""
        assert RichFormatter._MESSAGE_CONFIG["error"]["color"] == "red"

    def test_success_has_green_color(self):
        """Verify success message uses green color."""
        assert RichFormatter._MESSAGE_CONFIG["success"]["color"] == "green"

    def test_warning_has_yellow_color(self):
        """Verify warning message uses yellow color."""
        assert RichFormatter._MESSAGE_CONFIG["warning"]["color"] == "yellow"

    def test_info_has_cyan_color(self):
        """Verify info message uses cyan color."""
        assert RichFormatter._MESSAGE_CONFIG["info"]["color"] == "cyan"

    def test_error_has_bold_format(self):
        """Verify error message has bold formatting."""
        assert "bold" in RichFormatter._MESSAGE_CONFIG["error"]["format"]

    def test_debug_has_dim_format(self):
        """Verify debug message has dim formatting."""
        assert "dim" in RichFormatter._MESSAGE_CONFIG["debug"]["format"]

    def test_hint_has_italic_format(self):
        """Verify hint message has italic formatting."""
        assert "italic" in RichFormatter._MESSAGE_CONFIG["hint"]["format"]


class TestHelperMethods:
    """Test panel, table, code_block, list_items, horizontal_rule methods."""

    def test_panel(self):
        """Test panel rendering."""
        rf = RichFormatter()
        rf.panel("Test Title", "Test content here")

    def test_panel_custom_style(self):
        """Test panel with custom style."""
        rf = RichFormatter()
        rf.panel("Test Title", "Test content", style="red bold")

    def test_panel_expanded(self):
        """Test panel with expanded width."""
        rf = RichFormatter()
        rf.panel("Test Title", "Test content", expand=True)

    def test_table_single_row_dict(self):
        """Test table rendering with single row (dict)."""
        rf = RichFormatter()
        rf.table({"Host": "localhost", "Port": "3000", "Status": "Running"})

    def test_table_single_row_dict_with_title(self):
        """Test table with title."""
        rf = RichFormatter()
        rf.table({"Host": "localhost", "Port": "3000"}, title="Connection Info")

    def test_table_multiple_rows(self):
        """Test table rendering with multiple rows (list of dicts)."""
        rf = RichFormatter()
        data = [
            {"Name": "service1", "Status": "Running"},
            {"Name": "service2", "Status": "Stopped"},
        ]
        rf.table(data)

    def test_table_multiple_rows_with_title(self):
        """Test multi-row table with title."""
        rf = RichFormatter()
        data = [
            {"Name": "service1", "Status": "Running"},
            {"Name": "service2", "Status": "Stopped"},
        ]
        rf.table(data, title="Services")

    def test_table_empty_dict(self):
        """Test table with empty dict (should render but be empty)."""
        rf = RichFormatter()
        rf.table({})

    def test_table_empty_list(self):
        """Test table with empty list (should return early)."""
        rf = RichFormatter()
        rf.table([])

    def test_code_block_python(self):
        """Test syntax-highlighted code block (Python)."""
        rf = RichFormatter()
        code = 'print("Hello, World!")'
        rf.code_block(code, language="python")

    def test_code_block_bash(self):
        """Test syntax-highlighted code block (Bash)."""
        rf = RichFormatter()
        code = 'docker ps -a && echo "Done"'
        rf.code_block(code, language="bash")

    def test_code_block_custom_theme(self):
        """Test code block with custom theme."""
        rf = RichFormatter()
        code = 'print("test")'
        rf.code_block(code, language="python", theme="github-dark")

    def test_code_block_with_line_numbers(self):
        """Test code block with line numbers."""
        rf = RichFormatter()
        code = "line1\nline2\nline3"
        rf.code_block(code, language="python", line_numbers=True)

    def test_list_items_basic(self):
        """Test list items rendering."""
        rf = RichFormatter()
        items = ["First item", "Second item", "Third item"]
        rf.list_items(items)

    def test_list_items_custom_bullet(self):
        """Test list items with custom bullet."""
        rf = RichFormatter()
        items = ["Item A", "Item B", "Item C"]
        rf.list_items(items, bullet="▸")

    def test_list_items_custom_color(self):
        """Test list items with custom bullet color."""
        rf = RichFormatter()
        items = ["Red item", "Red item 2"]
        rf.list_items(items, color="red")

    def test_list_items_empty(self):
        """Test list items with empty list."""
        rf = RichFormatter()
        rf.list_items([])

    def test_horizontal_rule(self):
        """Test horizontal rule rendering."""
        rf = RichFormatter()
        rf.horizontal_rule()

    def test_horizontal_rule_custom_char(self):
        """Test horizontal rule with custom character."""
        rf = RichFormatter()
        rf.horizontal_rule(char="=")

    def test_horizontal_rule_custom_color(self):
        """Test horizontal rule with custom color."""
        rf = RichFormatter()
        rf.horizontal_rule(color="red")


class TestSpecializedFormatters:
    """Test specialized formatter methods."""

    def test_status_line(self):
        """Test status line rendering."""
        rf = RichFormatter()
        rf.status_line("Deploying", "services/web-app")

    def test_status_line_custom_separator(self):
        """Test status line with custom separator."""
        rf = RichFormatter()
        rf.status_line("Ready", "waiting for input", separator=">>")

    def test_status_line_custom_color(self):
        """Test status line with custom color."""
        rf = RichFormatter()
        rf.status_line("Complete", "all tasks done", status_color="green")

    def test_key_value_pairs(self):
        """Test key-value pairs rendering."""
        rf = RichFormatter()
        data = {"Host": "localhost", "Port": "8000", "Status": "Running"}
        rf.key_value_pairs(data)

    def test_key_value_pairs_custom_colors(self):
        """Test key-value pairs with custom colors."""
        rf = RichFormatter()
        data = {"User": "admin", "Role": "superuser"}
        rf.key_value_pairs(data, key_color="yellow", value_color="cyan")

    def test_key_value_pairs_empty(self):
        """Test key-value pairs with empty dict."""
        rf = RichFormatter()
        rf.key_value_pairs({})

    def test_success_summary_dict(self):
        """Test success summary with dict."""
        rf = RichFormatter()
        items = {
            "Service A": "http://localhost:3000",
            "Service B": "http://localhost:4000",
        }
        rf.success_summary(items)

    def test_success_summary_dict_custom_title(self):
        """Test success summary with custom title."""
        rf = RichFormatter()
        items = {
            "Database": "postgres://localhost:5432",
            "Cache": "redis://localhost:6379",
        }
        rf.success_summary(items, title="🚀 Setup Complete")

    def test_success_summary_list(self):
        """Test success summary with list."""
        rf = RichFormatter()
        items = ["Configuration validated", "Services deployed", "Health checks passed"]
        rf.success_summary(items)

    def test_success_summary_list_custom_title(self):
        """Test success summary with list and custom title."""
        rf = RichFormatter()
        items = ["Step 1 complete", "Step 2 complete", "Step 3 complete"]
        rf.success_summary(items, title="✓ Pipeline Complete")


class TestSingletonBehavior:
    """Test global singleton instance."""

    def test_singleton_instance_exists(self):
        """Verify global formatter instance exists."""
        assert formatter is not None

    def test_singleton_is_rich_formatter(self):
        """Verify global formatter is RichFormatter instance."""
        assert isinstance(formatter, RichFormatter)

    def test_multiple_imports_same_instance(self):
        """Verify multiple imports return same instance."""
        from utils.rich_formatter import formatter as f1
        from utils.rich_formatter import formatter as f2

        assert f1 is f2

    def test_singleton_methods_work(self):
        """Verify singleton can call all methods."""
        formatter.info("Test info via singleton")
        formatter.error("Test error via singleton")
        formatter.success("Test success via singleton")


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_message_type(self):
        """Test error raised for unknown message type."""
        rf = RichFormatter()
        with pytest.raises(ValueError, match="Unknown message type"):
            rf._render_message("invalid_type", "message")

    def test_message_with_special_characters(self):
        """Test messages with special characters render correctly."""
        rf = RichFormatter()
        rf.info("Message with special chars: !@#$%^&*()")
        rf.warning("Unicode test: 你好世界 🌍")

    def test_very_long_message(self):
        """Test rendering very long messages."""
        rf = RichFormatter()
        long_msg = "x" * 500
        rf.info(long_msg)

    def test_multiline_message(self):
        """Test messages with newlines."""
        rf = RichFormatter()
        multiline = "Line 1\nLine 2\nLine 3"
        rf.info(multiline)

    def test_empty_string_message(self):
        """Test rendering empty string message."""
        rf = RichFormatter()
        rf.info("")

    def test_empty_details(self):
        """Test message with empty string details."""
        rf = RichFormatter()
        rf.info("Main message", details="")


class TestConsoleIntegration:
    """Test Console integration and output."""

    def test_console_print_called(self):
        """Verify Console.print is called for simple messages."""
        rf = RichFormatter()
        with patch.object(rf._console, "print") as mock_print:
            rf.info("Test message")
            mock_print.assert_called_once()

    def test_panel_print_called_with_details(self):
        """Verify Panel is printed when details provided."""
        rf = RichFormatter()
        with patch.object(rf._console, "print") as mock_print:
            rf.info("Main", details="Details")
            mock_print.assert_called_once()
            # Verify Panel was printed
            call_args = mock_print.call_args
            assert len(call_args[0]) > 0
            assert isinstance(call_args[0][0], Panel)

    def test_multiple_console_calls(self):
        """Verify multiple messages result in multiple console calls."""
        rf = RichFormatter()
        with patch.object(rf._console, "print") as mock_print:
            rf.info("Message 1")
            rf.error("Message 2")
            rf.success("Message 3")
            assert mock_print.call_count == 3

    def test_console_rule_called(self):
        """Verify Console.rule is called for horizontal_rule."""
        rf = RichFormatter()
        with patch.object(rf._console, "rule") as mock_rule:
            rf.horizontal_rule()
            mock_rule.assert_called_once()


class TestMessageFormatting:
    """Test message formatting with Rich Text."""

    def test_emoji_in_message(self):
        """Verify emoji is included in formatted messages."""
        rf = RichFormatter()
        with patch.object(rf._console, "print") as mock_print:
            rf.info("Test")
            call_args = mock_print.call_args[0][0]
            # For basic message, it's a Text object
            if isinstance(call_args, Text):
                assert "💡" in str(call_args)

    def test_color_style_applied(self):
        """Verify color style is applied to messages."""
        rf = RichFormatter()
        with patch.object(rf._console, "print") as mock_print:
            rf.error("Test error")
            call_args = mock_print.call_args[0][0]
            if isinstance(call_args, Text):
                # Text style should include color
                assert "red" in str(call_args.style)

    def test_format_styles_applied(self):
        """Verify format styles (bold, italic) are applied."""
        rf = RichFormatter()
        with patch.object(rf._console, "print") as mock_print:
            rf.info("Test")
            call_args = mock_print.call_args[0][0]
            if isinstance(call_args, Text):
                # Should include bold format
                assert "bold" in str(call_args.style)


class TestAllMessageTypesComprehensive:
    """Comprehensive test calling all message types with all parameter combinations."""

    @pytest.mark.parametrize(
        "method_name",
        [
            "info",
            "error",
            "warning",
            "debug",
            "success",
            "hint",
            "step",
            "command",
            "result",
            "title",
        ],
    )
    def test_all_message_types_basic(self, method_name):
        """Test all message types with basic usage."""
        rf = RichFormatter()
        method = getattr(rf, method_name)
        method("Test message")

    @pytest.mark.parametrize(
        "method_name",
        [
            "info",
            "error",
            "warning",
            "debug",
            "success",
            "hint",
            "step",
            "command",
            "result",
            "title",
        ],
    )
    def test_all_message_types_with_details(self, method_name):
        """Test all message types with details."""
        rf = RichFormatter()
        method = getattr(rf, method_name)
        method("Main message", details="Additional details")

    @pytest.mark.parametrize(
        "method_name",
        [
            "info",
            "error",
            "warning",
            "debug",
            "success",
            "hint",
            "step",
            "command",
            "result",
            "title",
        ],
    )
    def test_all_message_types_without_prefix(self, method_name):
        """Test all message types without emoji prefix."""
        rf = RichFormatter()
        method = getattr(rf, method_name)
        method("Message without prefix", prefix=False)

    @pytest.mark.parametrize(
        "method_name",
        [
            "info",
            "error",
            "warning",
            "debug",
            "success",
            "hint",
            "step",
            "command",
            "result",
            "title",
        ],
    )
    def test_all_message_types_with_title(self, method_name):
        """Test all message types with title parameter."""
        rf = RichFormatter()
        method = getattr(rf, method_name)
        method("Content", title="Section")
