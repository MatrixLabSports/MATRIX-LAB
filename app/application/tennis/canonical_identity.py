from app.core.canonical_identity import SQLiteCanonicalIdentityRegistry


def register_tennis_entity(
    *,
    registry: SQLiteCanonicalIdentityRegistry,
    entity_type: str,
    canonical_key: str,
    display_name: str,
):
    entity = registry.build_entity(
        sport="tennis",
        entity_type=entity_type,
        canonical_key=canonical_key,
        display_name=display_name,
    )
    return registry.register(entity)
