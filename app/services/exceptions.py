from app.core import messages


class ConflictingIdentifiersError(Exception):
    def __init__(self, individual_ids: list[int]) -> None:
        self.individual_ids = individual_ids
        super().__init__("Identificadores informados correspondem a mais de um indivíduo.")


class InvalidBatchError(Exception):
    """Telemetry batch envelope violates the batch size contract."""


class EmptyBatchError(InvalidBatchError):
    def __init__(self) -> None:
        super().__init__(messages.EMPTY_BATCH)


class BatchTooLargeError(InvalidBatchError):
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        super().__init__(messages.BATCH_TOO_LARGE.format(max_eventos=max_size))
