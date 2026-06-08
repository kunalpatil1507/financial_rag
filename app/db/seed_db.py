"""
seed_db.py
==========
Creates default roles, permissions, and an admin user.
Run once after `init_db()`:
    python -m app.db.seed_db
"""
from app.db.database import SessionLocal, init_db
from app.models.role import Role, Permission
from app.models.user import User
from app.core.security import get_password_hash

PERMISSIONS = [
    ("documents:upload", "Upload new documents"),
    ("documents:read", "View documents"),
    ("documents:edit", "Edit document metadata"),
    ("documents:delete", "Delete documents"),
    ("documents:index", "Index documents for RAG"),
    ("rag:search", "Perform semantic search"),
    ("users:manage", "Manage users and roles"),
]

ROLES = {
    "Admin": list(range(len(PERMISSIONS))),  # all permissions
    "Analyst": [0, 1, 2, 4, 5],   # upload, read, edit, index, search
    "Auditor": [1, 5],             # read, search
    "Client": [1, 5],              # read, search
}

ADMIN_USER = {
    "email": "admin@example.com",
    "username": "admin",
    "password": "Admin@1234",
    "full_name": "System Administrator",
}


def seed():
    init_db()
    db = SessionLocal()

    try:
        # Create permissions
        perm_objects = []
        for name, desc in PERMISSIONS:
            perm = db.query(Permission).filter(Permission.name == name).first()
            if not perm:
                perm = Permission(name=name, description=desc)
                db.add(perm)
            perm_objects.append(perm)
        db.flush()

        # Create roles
        for role_name, perm_indices in ROLES.items():
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                role = Role(name=role_name)
                db.add(role)
                db.flush()
            role.permissions = [perm_objects[i] for i in perm_indices]

        # Create admin user
        admin = db.query(User).filter(User.username == ADMIN_USER["username"]).first()
        if not admin:
            admin = User(
                email=ADMIN_USER["email"],
                username=ADMIN_USER["username"],
                hashed_password=get_password_hash(ADMIN_USER["password"]),
                full_name=ADMIN_USER["full_name"],
            )
            db.add(admin)
            db.flush()

        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        if admin_role not in admin.roles:
            admin.roles.append(admin_role)

        db.commit()
        print("✅ Database seeded successfully.")
        print(f"   Admin credentials → username: {ADMIN_USER['username']}, password: {ADMIN_USER['password']}")

    except Exception as e:
        db.rollback()
        print(f"❌ Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
