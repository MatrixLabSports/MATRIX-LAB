from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalMatchIdentity:
    provider: str
    external_id: str

    def __post_init__(self):
        provider = self.provider.strip()
        external_id = self.external_id.strip()

        if not provider:
            raise ValueError(
                "provider no puede estar vacío."
            )

        if not external_id:
            raise ValueError(
                "external_id no puede estar vacío."
            )
