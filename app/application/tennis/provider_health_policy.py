from app.core.provider_health_policy import evaluate_provider_health


def evaluate_tennis_provider_health(
    *,
    snapshot,
    policy,
):
    return evaluate_provider_health(
        snapshot=snapshot,
        policy=policy,
        expected_sport="tennis",
    )
