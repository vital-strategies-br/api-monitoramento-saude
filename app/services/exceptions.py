class IdentificadoresConflitantesError(Exception):
    def __init__(self, individuo_ids: list[int]) -> None:
        self.individuo_ids = individuo_ids
        super().__init__("Identificadores informados correspondem a mais de um indivíduo.")
