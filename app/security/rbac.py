from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Permission(str, Enum):
    READ_RESEARCH = "read_research"
    RUN_RESEARCH = "run_research"
    VIEW_RISK = "view_risk"
    SUBMIT_HUMAN_REVIEW = "submit_human_review"
    MANAGE_SECURITY_POLICY = "manage_security_policy"
    VIEW_AUDIT = "view_audit"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "reader": frozenset({Permission.READ_RESEARCH}),
    "analyst": frozenset({Permission.READ_RESEARCH, Permission.RUN_RESEARCH, Permission.VIEW_RISK}),
    "operator": frozenset({Permission.READ_RESEARCH, Permission.VIEW_RISK, Permission.SUBMIT_HUMAN_REVIEW}),
    "security_admin": frozenset({Permission.MANAGE_SECURITY_POLICY, Permission.VIEW_AUDIT}),
    "auditor": frozenset({Permission.READ_RESEARCH, Permission.VIEW_RISK, Permission.VIEW_AUDIT}),
}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    roles: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.principal_id.strip():
            raise ValueError("principal_id is required")
        if not self.roles:
            raise ValueError("at least one role is required")
        unknown = set(self.roles) - set(ROLE_PERMISSIONS)
        if unknown:
            raise ValueError(f"unknown roles: {sorted(unknown)}")


def is_allowed(principal: Principal, permission: Permission) -> bool:
    return any(permission in ROLE_PERMISSIONS[role] for role in principal.roles)


def require(principal: Principal, permission: Permission) -> None:
    if not is_allowed(principal, permission):
        raise PermissionError(f"{principal.principal_id} lacks {permission.value}")
