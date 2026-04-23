from __future__ import annotations


class CollectionAccessDeniedError(Exception):
    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        super().__init__(f"Access denied to collection '{collection_name}'")


class IdentityProvisioningError(Exception):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code
        super().__init__(message)
