#!/usr/bin/env python3
"""
Wrapper script for backward compatibility.
"""
import sys
from mermaid_architect.cli import main, test_concurrent_write

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_concurrent_write()
        sys.exit(0)
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
