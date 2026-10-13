import sys

from .cli import main

if __name__ == "__main__":  # needed on Windows, where Evo Lab's worker processes import this module
    sys.exit(main())
