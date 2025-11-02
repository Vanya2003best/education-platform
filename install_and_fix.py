#!/usr/bin/env python3
"""
🚀 Education Platform - Automated Setup & Fix
This script will install dependencies and fix the login error
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, check=True):
    """Run a shell command"""
    print(f"   Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error: {e.stderr}")
        return False


def main():
    print("=" * 70)
    print("🚀 EDUCATION PLATFORM - AUTOMATED SETUP")
    print("=" * 70)

    # Check Python version
    print("\n1️⃣ Checking Python version...")
    if sys.version_info < (3, 7):
        print("   ❌ Python 3.7+ required")
        sys.exit(1)
    print(f"   ✅ Python {sys.version.split()[0]}")

    # Install pip packages
    print("\n2️⃣ Installing required packages...")
    packages = [
        "fastapi==0.104.1",
        "uvicorn[standard]==0.24.0",
        "python-multipart==0.0.6",
        "sqlalchemy==2.0.23",
        "psycopg2-binary==2.9.9",
        "asyncpg==0.29.0",
        "passlib[bcrypt]==1.7.4",
        "python-jose[cryptography]==3.3.0",
        "pydantic==2.5.0",
        "python-dotenv==1.0.0",
        "email-validator==2.1.0"
    ]

    for package in packages:
        if not run_command(f"pip install '{package}'", check=False):
            print(f"   ⚠️  Failed to install {package}")

    # Create .env file if not exists
    print("\n3️⃣ Setting up environment...")
    env_file = Path(".env")
    if not env_file.exists():
        env_content = """# Database
DATABASE_URL=sqlite:///./education.db

# Security
SECRET_KEY=your-secret-key-change-in-production-123456789
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Application
DEBUG=True
APP_NAME=Education Platform

# Initial settings
INITIAL_COINS=100
"""
        env_file.write_text(env_content)
        print("   ✅ Created .env file")
    else:
        print("   ✅ .env file exists")

    # Create database and users
    print("\n4️⃣ Setting up database...")

    setup_code = """
import sys
import os
sys.path.insert(0, os.getcwd())

from app.database import sync_engine, SessionLocal
from app.models import Base, User, UserRole
from app.auth import AuthService

# Create tables
Base.metadata.create_all(bind=sync_engine)
print("   ✅ Database tables created")

# Create users
db = SessionLocal()
try:
    # Check if users exist
    existing = db.query(User).filter(User.username == "student1").first()

    if not existing:
        users = [
            User(
                username="student1",
                email="student1@example.com",
                password_hash=AuthService.get_password_hash("student123"),
                full_name="Test Student",
                role=UserRole.STUDENT,
                coins=100,
                level=1,
                is_active=True,
                is_verified=True
            ),
            User(
                username="admin",
                email="admin@example.com",
                password_hash=AuthService.get_password_hash("admin123"),
                full_name="Administrator",
                role=UserRole.ADMIN,
                coins=1000,
                level=10,
                is_active=True,
                is_verified=True
            )
        ]

        for user in users:
            db.add(user)
        db.commit()
        print("   ✅ Test users created")
    else:
        # Fix passwords
        users = db.query(User).all()
        for user in users:
            if user.username == "student1":
                user.password_hash = AuthService.get_password_hash("student123")
            elif user.username == "admin":
                user.password_hash = AuthService.get_password_hash("admin123")
        db.commit()
        print("   ✅ User passwords fixed")

finally:
    db.close()
"""

    # Save and run setup code
    setup_file = Path("_temp_setup.py")
    setup_file.write_text(setup_code)

    try:
        run_command(f"python {setup_file}")
    except Exception as e:
        print(f"   ⚠️  Database setup error: {e}")
    finally:
        setup_file.unlink(missing_ok=True)

    # Test the setup
    print("\n5️⃣ Testing login...")

    test_code = """
import sys
import os
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal
from app.models import User
from app.auth import AuthService

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == "student1").first()
    if user:
        is_valid = AuthService.verify_password("student123", user.password_hash)
        if is_valid:
            print("   ✅ Login test PASSED")
        else:
            print("   ❌ Login test FAILED - password incorrect")
    else:
        print("   ❌ Login test FAILED - user not found")
finally:
    db.close()
"""

    test_file = Path("_temp_test.py")
    test_file.write_text(test_code)

    try:
        run_command(f"python {test_file}")
    except Exception as e:
        print(f"   ⚠️  Test error: {e}")
    finally:
        test_file.unlink(missing_ok=True)

    # Final instructions
    print("\n" + "=" * 70)
    print("✅ SETUP COMPLETE!")
    print("=" * 70)

    print("\n📋 Login Credentials:")
    print("   • Username: student1")
    print("   • Password: student123")
    print("\n   • Username: admin")
    print("   • Password: admin123")

    print("\n🚀 Start the server:")
    print("   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")

    print("\n🌐 Access the application:")
    print("   • Main: http://localhost:8000")
    print("   • API Docs: http://localhost:8000/api/docs")
    print("   • Test Page: http://localhost:8000/static/test.html")

    print("\n💡 If you still have issues:")
    print("   1. Check the server console for error messages")
    print("   2. Try the test server: python test_server.py")
    print("   3. Check browser DevTools (F12) for detailed errors")

    print("\n✨ Good luck with your Education Platform!")


if __name__ == "__main__":
    main()