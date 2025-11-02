#!/usr/bin/env python3
"""
🚀 QUICK FIX for Login Internal Server Error
Run this to immediately fix the authentication issue
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def quick_fix():
    print("🔧 QUICK FIX FOR LOGIN ERROR")
    print("=" * 60)

    try:
        # Import required modules
        from app.database import SessionLocal, sync_engine
        from app.models import Base, User, UserRole
        from app.auth import AuthService

        # Create tables if not exist
        print("\n1. Creating database tables...")
        Base.metadata.create_all(bind=sync_engine)
        print("   ✅ Tables ready")

        # Create or fix users
        print("\n2. Setting up users...")
        db = SessionLocal()

        # Check if student1 exists
        user = db.query(User).filter(User.username == "student1").first()

        if not user:
            # Create student1
            user = User(
                username="student1",
                email="student1@example.com",
                password_hash=AuthService.get_password_hash("student123"),
                full_name="Test Student",
                role=UserRole.STUDENT,
                coins=100,
                level=1,
                experience=0,
                is_active=True,
                is_verified=True
            )
            db.add(user)
            print("   ✅ Created user: student1")
        else:
            # Fix password
            user.password_hash = AuthService.get_password_hash("student123")
            user.is_active = True
            user.is_verified = True
            print("   ✅ Fixed user: student1")

        # Also create admin
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
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
            db.add(admin)
            print("   ✅ Created user: admin")

        db.commit()
        db.close()

        print("\n" + "=" * 60)
        print("✅ FIX COMPLETE!")
        print("=" * 60)
        print("\n📋 Login credentials:")
        print("   • student1 / student123")
        print("   • admin / admin123")
        print("\n🚀 Now restart your server:")
        print("   uvicorn app.main:app --reload")
        print("\n🌐 Then go to: http://localhost:8000")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n💡 Try running:")
        print("   1. pip install -r requirements.txt")
        print("   2. python reset_db.py")
        return False


if __name__ == "__main__":
    success = quick_fix()
    sys.exit(0 if success else 1)