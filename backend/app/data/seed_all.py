from app.data import seed_telco
from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
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
