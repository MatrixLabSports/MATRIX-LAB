def record_football_history_profile(
    *,
    store,
    profile,
):
    if profile.sport != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return store.record_profile(profile)
