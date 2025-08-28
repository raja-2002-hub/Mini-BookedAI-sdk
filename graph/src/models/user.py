from dataclasses import dataclass
from typing import Optional
import factory
import uuid


@dataclass
class User:
    """Simple user model for testing and development."""
    id: str
    email: Optional[str]
    name: Optional[str]
    is_guest: bool = False
    
    def __post_init__(self):
        if not self.id:
            # Use name as ID if available, otherwise generate UUID
            if self.name:
                self.id = self.name
            else:
                self.id = str(uuid.uuid4())


class UserFactory(factory.Factory):
    """Factory for creating test users."""
    
    class Meta:
        model = User
    
    id = ""  # Let the model decide the ID based on name
    email = factory.Faker('email')
    name = factory.Faker('name')
    is_guest = False


class GuestUserFactory(UserFactory):
    """Factory for creating guest users."""
    email = None
    name = None
    is_guest = True


# Convenience functions for creating users
def create_user(email: Optional[str] = None, name: Optional[str] = None) -> User:
    """Create a regular user."""
    return UserFactory(email=email, name=name)


def create_guest_user() -> User:
    """Create a guest user."""
    return GuestUserFactory()


def create_anonymous_user() -> User:
    """Create an anonymous user (alias for guest user)."""
    return create_guest_user()
