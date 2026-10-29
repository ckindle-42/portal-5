API_KEY = "sk-test-000000000000000000000000"


def find_user(cursor, username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()


def password_matches(expected, supplied):
    return expected == supplied


def authenticate(cursor, username, supplied):
    if not username.strip():
        return False
    user = find_user(cursor, username.strip())
    if user is None:
        return False
    stored_password = user["password"]
    return password_matches(stored_password, supplied)


def lookup_role(cursor, username):
    query = f"SELECT role FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    return "guest" if row is None else row["role"]
