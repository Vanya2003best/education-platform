#!/usr/bin/env python3
"""
🔍 Comprehensive Authentication Diagnostics
This will identify exactly why login is failing
"""

import sys
import os
import asyncio
import traceback

# Add current directory to path
sys.path.insert(0, os.getcwd())


async def test_authentication_flow():
    """Test the complete authentication flow"""

    print("=" * 70)
    print("🔍 AUTHENTICATION FLOW DIAGNOSTICS")
    print("=" * 70)

    # 1. Test imports
    print("\n1️⃣ Testing imports...")
    try:
        from app.database import get_async_db, AsyncSessionLocal
        print("   ✅ Database imports OK")
    except ImportError as e:
        print(f"   ❌ Database import failed: {e}")
        return

    try:
        from app.models import User, UserRole
        print("   ✅ Models import OK")
    except ImportError as e:
        print(f"   ❌ Models import failed: {e}")
        return

    try:
        from app.auth import AuthService
        print("   ✅ AuthService import OK")
    except ImportError as e:
        print(f"   ❌ AuthService import failed: {e}")
        return

    # 2. Test database connection
    print("\n2️⃣ Testing database connection...")
    try:
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
            print(f"   ✅ Database connected, found {len(users)} users")

            for user in users[:3]:
                print(f"      • {user.username} (role: {user.role})")
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        traceback.print_exc()
        return

    # 3. Test password hashing
    print("\n3️⃣ Testing password hashing...")
    try:
        test_password = "test123"
        hashed = AuthService.get_password_hash(test_password)
        is_valid = AuthService.verify_password(test_password, hashed)

        if is_valid:
            print("   ✅ Password hashing works")
        else:
            print("   ❌ Password verification failed")
    except Exception as e:
        print(f"   ❌ Password hashing error: {e}")
        traceback.print_exc()

    # 4. Test specific user login
    print("\n4️⃣ Testing login for 'admin'...")
    try:
        async with AsyncSessionLocal() as db:
            # Get admin user
            result = await db.execute(
                select(User).where(User.username == "admin")
            )
            admin = result.scalar_one_or_none()

            if not admin:
                print("   ❌ Admin user not found")
                return

            print(f"   ✓ Admin found: {admin.username}")
            print(f"   ✓ Email: {admin.email}")
            print(f"   ✓ Role: {admin.role}")
            print(f"   ✓ Role type: {type(admin.role)}")

            # Test password
            try:
                is_valid = AuthService.verify_password("admin123", admin.password_hash)
                if is_valid:
                    print("   ✅ Password verification: SUCCESS")
                else:
                    print("   ❌ Password verification: FAILED")
                    print("      Fixing password...")
                    admin.password_hash = AuthService.get_password_hash("admin123")
                    await db.commit()
                    print("      ✅ Password fixed")
            except Exception as e:
                print(f"   ❌ Password verification error: {e}")
                traceback.print_exc()

            # Test token creation
            try:
                role_value = admin.role.value if hasattr(admin.role, 'value') else str(admin.role)
                print(f"   ✓ Role value for token: {role_value}")

                tokens = AuthService.create_tokens(admin.id, role_value)
                if tokens.get('access_token'):
                    print("   ✅ Token creation: SUCCESS")
                    print(f"      Token preview: {tokens['access_token'][:50]}...")
                else:
                    print("   ❌ Token creation: FAILED")
            except Exception as e:
                print(f"   ❌ Token creation error: {e}")
                traceback.print_exc()

    except Exception as e:
        print(f"   ❌ Login tests error: {e}")
        traceback.print_exc()

    # 5. Test the actual login function
    print("\n5️⃣ Testing actual login function...")
    try:
        from app.routers.auth import login
        from fastapi.security import OAuth2PasswordRequestForm

        # Create mock form data
        class MockFormData:
            def __init__(self):
                self.username = "admin"
                self.password = "admin123"
                self.scope = ""
                self.client_id = None
                self.client_secret = None

        form_data = MockFormData()

        async with AsyncSessionLocal() as db:
            try:
                result = await login(form_data, db)
                print("   ✅ Login function: SUCCESS")
                print(f"      Result: {result}")
            except Exception as e:
                print(f"   ❌ Login function error: {e}")
                traceback.print_exc()

    except ImportError as e:
        print(f"   ⚠️ Could not import login function: {e}")
    except Exception as e:
        print(f"   ❌ Login function tests error: {e}")
        traceback.print_exc()


def check_configuration():
    """Check configuration settings"""

    print("\n6️⃣ Checking configuration...")

    try:
        from app.config import settings

        print(f"   • SECRET_KEY: {'SET' if settings.SECRET_KEY else 'NOT SET'}")
        print(f"   • ALGORITHM: {settings.ALGORITHM}")
        print(f"   • DATABASE_URL: {settings.DATABASE_URL[:30]}...")
        print(f"   • INITIAL_COINS: {settings.INITIAL_COINS}")

        if not settings.SECRET_KEY:
            print("   ❌ SECRET_KEY not configured!")
        else:
            print("   ✅ Configuration looks OK")

    except Exception as e:
        print(f"   ❌ Configuration error: {e}")


def suggest_fixes():
    """Suggest fixes based on diagnostics"""

    print("\n" + "=" * 70)
    print("💡 SUGGESTED FIXES")
    print("=" * 70)

    print("""
1. If password verification failed:
   python quick_fix.py

2. If imports are failing:
   pip install -r requirements.txt

3. If database connection failed:
   python reset_db.py

4. To tests with minimal server:
   python test_server_fixed.py
   (then visit http://localhost:8001/test)

5. For a complete fresh start:
   python fix_auth_direct.py

6. Check server logs:
   uvicorn app.main:app --reload --log-level debug
""")


def main():
    print("\n🚀 Starting Authentication Diagnostics\n")

    # Run async tests
    asyncio.run(test_authentication_flow())

    # Check configuration
    check_configuration()

    # Suggest fixes
    suggest_fixes()

    print("\n✨ Diagnostics complete!\n")


if __name__ == "__main__":
    main()