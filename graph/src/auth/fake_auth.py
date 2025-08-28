from typing import Optional, Dict
import uuid
from ..models.user import User, UserFactory, GuestUserFactory, create_user, create_guest_user


class FakeAuthService:
    """Simple fake authentication service for development and testing."""
    
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._session_tokens: Dict[str, str] = {}  # token -> user_id
    
    def create_user(self, email: Optional[str] = None, name: Optional[str] = None) -> User:
        """Create a new user."""
        user = create_user(email=email, name=name)
        self._users[user.id] = user
        return user
    
    def create_guest_user(self) -> User:
        """Create a new guest user."""
        user = create_guest_user()
        self._users[user.id] = user
        return user
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self._users.get(user_id)
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        for user in self._users.values():
            if user.email == email:
                return user
        return None
    
    def create_session_token(self, user_id: str) -> str:
        """Create a session token for a user."""
        token = str(uuid.uuid4())
        self._session_tokens[token] = user_id
        return token
    
    def get_user_from_token(self, token: str) -> Optional[User]:
        """Get user from session token."""
        user_id = self._session_tokens.get(token)
        if user_id:
            return self.get_user_by_id(user_id)
        return None
    
    def validate_token(self, token: str) -> bool:
        """Validate if a token exists."""
        return token in self._session_tokens
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a session token."""
        if token in self._session_tokens:
            del self._session_tokens[token]
            return True
        return False
    
    def get_or_create_anonymous_user(self) -> User:
        """Get or create an anonymous user for the current session."""
        # For simplicity, always create a new guest user
        # In a real implementation, you might want to persist this
        return self.create_guest_user()


# Global instance
fake_auth = FakeAuthService()


# Convenience functions
def get_current_user(token: Optional[str] = None) -> User:
    """Get current user from token, or create anonymous user if no token."""
    if token:
        user = fake_auth.get_user_from_token(token)
        if user:
            return user
    return fake_auth.get_or_create_anonymous_user()


def create_test_user(email: Optional[str] = None, name: Optional[str] = None) -> User:
    """Create a test user."""
    return fake_auth.create_user(email=email, name=name)


def create_test_guest() -> User:
    """Create a test guest user."""
    return fake_auth.create_guest_user()


def get_or_create_user_by_name(name: str) -> User:
    """Get or create a user by name. If user exists, return existing user."""
    # Check if user already exists
    for user in fake_auth._users.values():
        if user.name == name:
            return user
    
    # Create new user with the given name
    email = f"{name.lower()}@test.com"
    return fake_auth.create_user(email=email, name=name)
