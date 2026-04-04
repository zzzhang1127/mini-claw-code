"""Math utility functions for prime numbers, factorials, and Fibonacci sequences."""

from typing import Union


def is_prime(n: int) -> bool:
    """
    Check if a number is prime.
    
    Args:
        n: The number to check.
        
    Returns:
        True if n is prime, False otherwise.
        
    Examples:
        >>> is_prime(2)
        True
        >>> is_prime(17)
        True
        >>> is_prime(4)
        False
        >>> is_prime(1)
        False
    """
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    for i in range(3, int(n ** 0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def factorial(n: int) -> int:
    """
    Calculate the factorial of a non-negative integer.
    
    Args:
        n: A non-negative integer.
        
    Returns:
        The factorial of n (n!).
        
    Raises:
        ValueError: If n is negative.
        
    Examples:
        >>> factorial(0)
        1
        >>> factorial(5)
        120
        >>> factorial(3)
        6
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def fibonacci(n: int) -> int:
    """
    Calculate the nth Fibonacci number.
    
    The Fibonacci sequence starts with F(0) = 0, F(1) = 1,
    and each subsequent number is the sum of the two preceding ones.
    
    Args:
        n: The position in the Fibonacci sequence (0-indexed).
        
    Returns:
        The nth Fibonacci number.
        
    Raises:
        ValueError: If n is negative.
        
    Examples:
        >>> fibonacci(0)
        0
        >>> fibonacci(1)
        1
        >>> fibonacci(10)
        55
        >>> fibonacci(20)
        6765
    """
    if n < 0:
        raise ValueError("Fibonacci is not defined for negative indices")
    if n == 0:
        return 0
    if n == 1:
        return 1
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def main() -> None:
    """Run example usage of the math utility functions."""
    print("=" * 50)
    print("Math Utilities - Example Usage")
    print("=" * 50)
    
    # Prime number examples
    print("\n--- Prime Number Check ---")
    test_numbers = [1, 2, 3, 4, 5, 17, 25, 97, 100]
    for num in test_numbers:
        result = "prime" if is_prime(num) else "not prime"
        print(f"  {num} is {result}")
    
    # Factorial examples
    print("\n--- Factorial Calculation ---")
    for i in range(6):
        print(f"  {i}! = {factorial(i)}")
    
    # Fibonacci examples
    print("\n--- Fibonacci Sequence ---")
    print("First 15 Fibonacci numbers:")
    fib_sequence = [fibonacci(i) for i in range(15)]
    print(f"  {fib_sequence}")
    print(f"\n  fibonacci(20) = {fibonacci(20)}")
    print(f"  fibonacci(30) = {fibonacci(30)}")
    
    print("\n" + "=" * 50)
    print("All examples completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
