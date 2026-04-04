"""Unit tests for mypackage.utils module."""

import unittest

from mypackage.utils import greet, capitalize_words, reverse_string


class TestGreet(unittest.TestCase):
    """Test cases for the greet function."""

    def test_greet_with_name(self) -> None:
        """Test greeting a person by name."""
        result = greet("Alice")
        self.assertEqual(result, "Hello, Alice!")

    def test_greet_with_empty_string(self) -> None:
        """Test greeting with an empty string."""
        result = greet("")
        self.assertEqual(result, "Hello, !")


class TestCapitalizeWords(unittest.TestCase):
    """Test cases for the capitalize_words function."""

    def test_capitalize_single_word(self) -> None:
        """Test capitalizing a single word."""
        result = capitalize_words("hello")
        self.assertEqual(result, "Hello")

    def test_capitalize_multiple_words(self) -> None:
        """Test capitalizing multiple words."""
        result = capitalize_words("hello world")
        self.assertEqual(result, "Hello World")

    def test_capitalize_already_capitalized(self) -> None:
        """Test capitalizing already capitalized words."""
        result = capitalize_words("Hello World")
        self.assertEqual(result, "Hello World")


class TestReverseString(unittest.TestCase):
    """Test cases for the reverse_string function."""

    def test_reverse_simple_string(self) -> None:
        """Test reversing a simple string."""
        result = reverse_string("hello")
        self.assertEqual(result, "olleh")

    def test_reverse_palindrome(self) -> None:
        """Test reversing a palindrome."""
        result = reverse_string("radar")
        self.assertEqual(result, "radar")

    def test_reverse_empty_string(self) -> None:
        """Test reversing an empty string."""
        result = reverse_string("")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
