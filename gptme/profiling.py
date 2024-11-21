"""
Profiling utilities for performance analysis
"""

import cProfile
import pstats
from pathlib import Path
from functools import wraps
from typing import Callable, TypeVar, ParamSpec

P = ParamSpec('P')
T = TypeVar('T')

def profile(output_file: str | Path) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to profile a function and save results to a file.
    
    Usage:
        @profile("my_function.prof")
        def my_function():
            ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            profiler = cProfile.Profile()
            try:
                return profiler.runcall(func, *args, **kwargs)
            finally:
                # Convert Path to string if needed
                stats_file = str(output_file) if isinstance(output_file, Path) else output_file
                profiler.dump_stats(stats_file)
                # Print summary
                stats = pstats.Stats(stats_file)
                stats.strip_dirs().sort_stats('cumulative').print_stats(30)
        return wrapper
    return decorator

def analyze_profile(profile_file: str | Path) -> None:
    """
    Analyze a profile file and print detailed statistics.
    """
    stats = pstats.Stats(profile_file)
    stats.strip_dirs()
    
    print("\n=== Time Ordered ===")
    stats.sort_stats('time').print_stats(20)
    
    print("\n=== Cumulative Time ===")
    stats.sort_stats('cumulative').print_stats(20)
    
    print("\n=== Call Count ===")
    stats.sort_stats('calls').print_stats(20)
    
    print("\n=== Function Name ===")
    stats.sort_stats('name').print_stats(20)
