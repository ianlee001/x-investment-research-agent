from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    run_id: str
    user_id: str = "local"
