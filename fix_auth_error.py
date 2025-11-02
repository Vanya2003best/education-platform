#!/usr/bin/env python3
"""
🔧 Education Platform - Authentication Error Fix Script
This script will diagnose and fix the Internal Server Error during login
"""

import sys
import os
import traceback
from pathlib import Path


def diagnose_issue():
    """Diagnose the authentication issue"""

    print("=" * 70)
    print("🔍 EDUCATION PLATFORM - AUTHENTICATION ERROR DIAGNOSIS")
    print("=" * 70)

    issues_found = []

    # 1. Check if database module exists
    print("\n1️⃣ Checking database connection...")
    try:
        from app.database import SessionLocal, sync_engine
        from sqlalchemy import text

        db = SessionLocal()
        result = db.execute(text("SELECT 1"))
        db.close()
        print("   ✅ Database connection: OK")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        issues_found.append("import_error")
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
        issues_found.append("db_connection")

    # 2. Check authentication module
    print("\n2️⃣ Checking authentication module...")
    try:
        from app.auth import AuthService
        from app.models import User, UserRole

        # Test password hashing
        test_hash = AuthService.get_password_hash("test123")
        is_valid = AuthService.verify_password("test123", test_hash)

        if is_valid:
            print("   ✅ Password hashing: OK")
        else:
            print("   ❌ Password hashing: FAILED")
            issues_found.append("password_hashing")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        issues_found.append("auth_import")
    except Exception as e:
        print(f"   ❌ Authentication error: {e}")
        issues_found.append("auth_error")

    # 3. Check if users exist
    print("\n3️⃣ Checking users in database...")
    try:
        from app.database import SessionLocal
        from app.models import User

        db = SessionLocal()
        users = db.query(User).all()
        db.close()

        if users:
            print(f"   ✅ Found {len(users)} users")
            for user in users[:3]:
                print(f"      • {user.username}")
        else:
            print("   ⚠️  No users found in database")
            issues_found.append("no_users")
    except Exception as e:
        print(f"   ❌ Error checking users: {e}")
        issues_found.append("user_check_error")

    # 4. Check main app
    print("\n4️⃣ Checking main application...")
    try:
        from app.main import app
        print("   ✅ Main app imports: OK")
    except ImportError as e:
        print(f"   ❌ Main app import error: {e}")
        issues_found.append("main_app_error")

    return issues_found


def fix_issues(issues):
    """Fix identified issues"""

    print("\n" + "=" * 70)
    print("🔧 APPLYING FIXES")
    print("=" * 70)

    if not issues:
        print("\n✅ No issues found! The error might be intermittent.")
        print("   Try restarting the server: uvicorn app.main:app --reload")
        return

    # Fix database connection
    if "db_connection" in issues:
        print("\n🔧 Fixing database connection...")
        try:
            from app.database import sync_engine
            from app.models import Base

            # Create tables
            Base.metadata.create_all(bind=sync_engine)
            print("   ✅ Database tables created")
        except Exception as e:
            print(f"   ❌ Could not fix database: {e}")

    # Fix missing users
    if "no_users" in issues or "user_check_error" in issues:
        print("\n🔧 Creating tests users...")
        try:
            from app.database import SessionLocal
            from app.models import User, UserRole
            from app.auth import AuthService

            db = SessionLocal()

            # Check if users exist
            existing = db.query(User).filter(User.username == "student1").first()

            if not existing:
                # Create tests users
                users = [
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
                    ),
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
                        username="teacher",
                        email="teacher@example.com",
                        password_hash=AuthService.get_password_hash("teacher123"),
                        full_name="Test Teacher",
                        role=UserRole.TEACHER,
                        coins=500,
                        level=5,
                        is_active=True,
                        is_verified=True
                    )
                ]

                for user in users:
                    db.add(user)

                db.commit()
                print("   ✅ Created tests users:")
                print("      • admin / admin123")
                print("      • student1 / student123")
                print("      • teacher / teacher123")
            else:
                # Fix existing users' passwords
                users = db.query(User).all()
                for user in users:
                    if user.username == "admin":
                        user.password_hash = AuthService.get_password_hash("admin123")
                    elif user.username == "student1":
                        user.password_hash = AuthService.get_password_hash("student123")
                    elif user.username == "teacher":
                        user.password_hash = AuthService.get_password_hash("teacher123")

                db.commit()
                print("   ✅ Fixed passwords for existing users")

            db.close()

        except Exception as e:
            print(f"   ❌ Could not create users: {e}")
            traceback.print_exc()


def test_login():
    """Test login functionality"""

    print("\n" + "=" * 70)
    print("🧪 TESTING LOGIN")
    print("=" * 70)

    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.models import User
        from app.auth import AuthService
        from sqlalchemy import select

        async def test():
            async with AsyncSessionLocal() as db:
                # Test with student1
                result = await db.execute(
                    select(User).where(User.username == "student1")
                )
                user = result.scalar_one_or_none()

                if user:
                    is_valid = AuthService.verify_password("student123", user.password_hash)
                    if is_valid:
                        print("   ✅ Login tests PASSED for student1/student123")

                        # Test token creation
                        tokens = AuthService.create_tokens(user.id, user.role.value)
                        if tokens.get("access_token"):
                            print("   ✅ Token generation PASSED")
                        else:
                            print("   ❌ Token generation FAILED")
                    else:
                        print("   ❌ Password verification FAILED")
                else:
                    print("   ❌ User 'student1' not found")

        asyncio.run(test())

    except Exception as e:
        print(f"   ❌ Login tests failed: {e}")
        traceback.print_exc()


def check_requirements():
    """Check if all required packages are installed"""

    print("\n" + "=" * 70)
    print("📦 CHECKING REQUIREMENTS")
    print("=" * 70)

    required = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "passlib",
        "python-jose",
        "python-multipart"
    ]

    missing = []
    for package in required:
        try:
            __import__(package.replace("-", "_"))
            print(f"   ✅ {package}: installed")
        except ImportError:
            print(f"   ❌ {package}: MISSING")
            missing.append(package)

    if missing:
        print(f"\n   ⚠️  Install missing packages:")
        print(f"      pip install {' '.join(missing)}")

    return len(missing) == 0


def main():
    """Main function"""

    print("\n🚀 Starting Education Platform Authentication Fix\n")

    # Add app directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Check requirements
    if not check_requirements():
        print("\n❌ Please install missing requirements first!")
        return

    # Diagnose issues
    issues = diagnose_issue()

    # Fix issues
    fix_issues(issues)

    # Test login
    test_login()

    # Final instructions
    print("\n" + "=" * 70)
    print("📋 NEXT STEPS")
    print("=" * 70)
    print("\n1. Restart your server:")
    print("   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    print("\n2. Try logging in with:")
    print("   Username: student1")
    print("   Password: student123")
    print("\n3. If still not working, check server logs for detailed error")
    print("\n4. Alternative: Use the tests endpoint:")
    print("   http://localhost:8000/static/test.html")
    print("\n✨ Good luck!")


if __name__ == "__main__":
    main()