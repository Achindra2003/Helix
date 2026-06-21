"""Uniform error shape:  { "error": { "code", "message" } }  (contract §1)."""
from fastapi import HTTPException


def api_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})
