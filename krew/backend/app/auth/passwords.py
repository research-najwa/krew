"""Password hashing with bcrypt via passlib."""
import asyncio

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


async def hash_password_async(plain: str) -> str:
    return await asyncio.to_thread(pwd_context.hash, plain)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(pwd_context.verify, plain, hashed)
