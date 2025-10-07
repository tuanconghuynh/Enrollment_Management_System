from .session import init_db

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("✅ Database tables created successfully.")
