def password_matches(expected, supplied):
    return secrets.compare_digest(expected, supplied.lower())  # noqa: F821
