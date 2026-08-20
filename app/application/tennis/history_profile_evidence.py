def record_tennis_history_profile(
    *,
    store,
    profile,
):
    if profile.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return store.record_profile(profile)
