from auth import password_matches


def test_password_matches_exact_text():
    assert password_matches("Portal5", "Portal5")


def test_password_comparison_is_case_sensitive():
    assert not password_matches("Portal5", "portal5")
