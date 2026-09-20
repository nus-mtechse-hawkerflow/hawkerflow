from models.hawker_details import HawkerDetails
from repository.hawker_repository import HawkerRepository


class HawkerService:
    def __init__(self, repo: HawkerRepository):
        self._repo = repo

    def create_hawker(self, hawker_details: HawkerDetails):
        return self._repo.create_hawker(hawker_details)

    def get_all_hawker(self):
        stalls = self._repo.get_all_hawker()
        return stalls