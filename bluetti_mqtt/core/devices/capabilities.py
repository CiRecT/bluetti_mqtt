from dataclasses import dataclass, field
from typing import Any, Optional

from ..commands import WriteSingleRegister


@dataclass(frozen=True)
class ExecutionPolicy:
    timeout: float = 5
    max_attempts: int = 5
    minimum_update_interval: int = 0
    dispatch_timeout: Optional[float] = None
    requires_same_connection: bool = False


@dataclass(frozen=True)
class WriteOnlyField:
    name: str
    address: int
    minimum: int
    maximum: int
    step: int = 1
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)

    def build_command(self, value: Any) -> WriteSingleRegister:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{self.name} requires an integer')
        if value < self.minimum or value > self.maximum:
            raise ValueError(f'{self.name} must be between {self.minimum} and {self.maximum}')
        if (value - self.minimum) % self.step != 0:
            raise ValueError(f'{self.name} must use step {self.step}')
        return WriteSingleRegister(self.address, value)
