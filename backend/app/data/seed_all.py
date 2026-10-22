from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        # Telco seeding is wired in Task 10; nothing to seed for now.
        print("Seeded 0 rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
