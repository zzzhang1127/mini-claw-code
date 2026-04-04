"""Utility functions for common string operations."""


def greet(name: str) -> str:
    """Greet a person by name.

    Args:
        name: The name of the person to greet.

    Returns:
        A greeting message.
    """
    return f"Hello, {name}!"


def capitalize_words(text: str) -> str:
    """Capitalize the first letter of each word in a string.

    Args:
        text: The input string to process.

    Returns:
        The string with each word capitalized.
    """
    return text.title()


def reverse_string(text: str) -> str:
    """Reverse a string.

    Args:
        text: The input string to reverse.

    Returns:
        The reversed string.
    """
    return text[::-1]
