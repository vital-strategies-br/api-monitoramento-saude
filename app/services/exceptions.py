class ConflictingIdentifiersError(Exception):
    def __init__(self, individual_ids: list[int]) -> None:
        self.individual_ids = individual_ids
        super().__init__("Identificadores informados correspondem a mais de um indivíduo.")
