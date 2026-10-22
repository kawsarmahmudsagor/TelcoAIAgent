"""One-off CLI to generate a bcrypt hash for ADMIN_PASSWORD_HASH in .env.

Usage: python -m app.scripts.hash_password "yourpassword"
"""

import sys

from app.services.auth_service import hash_password


def main() -> None:
    if len(sys.argv) != 2:
        print('Usage: python -m app.scripts.hash_password "yourpassword"')
        raise SystemExit(1)
    print(hash_password(sys.argv[1]))


if __name__ == "__main__":
    main()
