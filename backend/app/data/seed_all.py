import argparse

from app.data import seed_telco
from app.db.session import SessionLocal


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed the telco demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the existing demo rows first and reseed relative to now "
        "(01999 test subscribers, agent config, conversations and RAG are kept)",
    )
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        if args.reset:
            gone = seed_telco.clear(db)
            print(
                f"Cleared {gone['subscribers']} subscribers, {gone['incidents']} incidents, "
                f"{gone['offers']} offers, {gone['packages']} packages."
            )
        n = seed_telco.seed(db)
        db.commit()
        print(
            f"Seeded {n['subscribers']} subscribers, {n['packages']} packages, "
            f"{n['transactions']} transactions, {n['cases']} cases, "
            f"{n['incidents']} incidents, {n['offers']} offers."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
