"""Local demo identity only. Never use with real customer data."""
from dataclasses import dataclass

from fastapi import HTTPException

from app.models import Organization, OrganizationMembership, User


@dataclass(frozen=True)
class DemoIdentity:
    user: User
    organization: Organization
    membership: OrganizationMembership

    def require_manager(self):
        if self.membership.role not in ("OWNER", "MANAGER"):
            raise HTTPException(403, "An owner or manager role is required.")
        return self.organization
