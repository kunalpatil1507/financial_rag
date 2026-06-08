from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.models.role import Role, Permission
from app.models.user import User
from app.schemas.schemas import RoleCreate, RoleOut, AssignRoleRequest, PermissionOut
from app.core.security import get_current_user, require_role

router = APIRouter(tags=["Roles & Permissions"])


# ─── Role CRUD ────────────────────────────────────────────────────────────────

@router.post("/roles/create", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("Admin")),
):
    """Create a new role with permissions (Admin only)."""
    if db.query(Role).filter(Role.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(name=payload.name, description=payload.description)

    # Attach permissions
    for perm_name in payload.permission_names:
        perm = db.query(Permission).filter(Permission.name == perm_name).first()
        if not perm:
            perm = Permission(name=perm_name)
            db.add(perm)
        role.permissions.append(perm)

    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("/roles", response_model=List[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """List all available roles."""
    return db.query(Role).all()


# ─── User Role Assignment ─────────────────────────────────────────────────────

@router.post("/users/assign-role", response_model=dict)
def assign_role(
    payload: AssignRoleRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("Admin")),
):
    """Assign a role to a user (Admin only)."""
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = db.query(Role).filter(Role.name == payload.role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role in user.roles:
        raise HTTPException(status_code=400, detail="User already has this role")

    user.roles.append(role)
    db.commit()
    return {"message": f"Role '{role.name}' assigned to user '{user.username}'"}


@router.get("/users/{user_id}/roles", response_model=List[RoleOut])
def get_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get roles assigned to a user."""
    # Users can view their own roles; admins can view anyone's
    admin_role_names = {r.name for r in current_user.roles}
    if current_user.id != user_id and "Admin" not in admin_role_names:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.roles


@router.get("/users/{user_id}/permissions", response_model=List[PermissionOut])
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """View all permissions for a user (aggregated from all their roles)."""
    admin_role_names = {r.name for r in current_user.roles}
    if current_user.id != user_id and "Admin" not in admin_role_names:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    seen_ids = set()
    permissions = []
    for role in user.roles:
        for perm in role.permissions:
            if perm.id not in seen_ids:
                seen_ids.add(perm.id)
                permissions.append(perm)
    return permissions
