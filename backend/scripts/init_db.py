from __future__ import annotations

from sqlalchemy import select

from app.core.security import hash_password
from app.domain.enum import OrgType
from app.infra.database.models import (
    Organization,
    Permission,
    Role,
    RolePermission,
    SkillDictionary,
    User,
)
from app.infra.database.session import SessionLocal, create_db_schema

DEFAULT_SKILLS = [
    ("python", ["py", "python3"]),
    ("fastapi", ["fast api"]),
    ("postgresql", ["postgres", "psql"]),
    ("redis", []),
    ("kafka", ["apache kafka"]),
    ("docker", []),
    ("react", ["reactjs"]),
    ("typescript", ["ts"]),
    ("machine learning", ["ml"]),
    ("llm", ["large language model", "genai"]),
]

DEFAULT_PERMISSIONS = [
    ("org", "create"),
    ("job", "create"),
    ("job", "moderate"),
    ("cv", "mask"),
    ("student", "create"),
    ("ai", "use"),
]


def main() -> None:
    create_db_schema()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@c2.local"))
        if not admin:
            admin = User(
                email="admin@c2.local",
                full_name="C2 Platform Admin",
                password_hash=hash_password("ChangeMe123!"),
            )
            db.add(admin)

        university = db.scalar(select(Organization).where(Organization.name == "Demo University"))
        if not university:
            university = Organization(
                name="Demo University",
                type=OrgType.UNIVERSITY,
                is_verified_partner=True,
                metadata_json={"seed": True},
            )
            db.add(university)

        permissions: list[Permission] = []
        for resource, action in DEFAULT_PERMISSIONS:
            permission = db.scalar(
                select(Permission).where(
                    Permission.resource == resource,
                    Permission.action == action,
                )
            )
            if not permission:
                permission = Permission(resource=resource, action=action)
                db.add(permission)
            permissions.append(permission)

        db.flush()
        role = db.scalar(select(Role).where(Role.org_id.is_(None), Role.name == "super_admin"))
        if not role:
            role = Role(org_id=None, name="super_admin")
            db.add(role)
            db.flush()

        for permission in permissions:
            exists = db.get(RolePermission, {"role_id": role.id, "permission_id": permission.id})
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        for name, synonyms in DEFAULT_SKILLS:
            skill = db.scalar(select(SkillDictionary).where(SkillDictionary.name == name))
            if not skill:
                db.add(SkillDictionary(name=name, synonyms=synonyms))

        db.commit()
        print("Database initialized. Demo admin: admin@c2.local / ChangeMe123!")


if __name__ == "__main__":
    main()
