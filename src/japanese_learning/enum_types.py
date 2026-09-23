from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator

EnumT = TypeVar("EnumT", bound=StrEnum)


class StrEnumType(TypeDecorator[EnumT]):
    """将单个 StrEnum 以字符串形式存入数据库，并在读取时恢复为枚举。"""

    impl = Text
    cache_ok = True

    def __init__(self, enum_type: type[EnumT]) -> None:
        super().__init__()
        self.enum_type = enum_type

    def process_bind_param(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        return self.enum_type(value).value

    def process_result_value(self, value: object, dialect: object) -> EnumT | None:
        if value is None:
            return None
        return self.enum_type(value)


class StrEnumListJSON(TypeDecorator[list[EnumT]]):
    """将 StrEnum 列表以 JSON 字符串数组存入数据库，并恢复为枚举列表。"""

    impl = JSON
    cache_ok = True

    def __init__(self, enum_type: type[EnumT]) -> None:
        super().__init__()
        self.enum_type = enum_type

    def process_bind_param(
        self,
        value: object,
        dialect: object,
    ) -> list[str]:
        if not value:
            return []
        return [self.enum_type(item).value for item in value]  # type: ignore[union-attr]

    def process_result_value(
        self,
        value: object,
        dialect: object,
    ) -> list[EnumT]:
        if not value:
            return []
        return [self.enum_type(item) for item in value]  # type: ignore[union-attr]
