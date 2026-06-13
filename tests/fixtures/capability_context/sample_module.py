"""Sample ~realistic module for D4 long-context comprehension probe.

The probe embeds this file ahead of the prompt; the model must add ONE new
function without disturbing the existing code.
"""
from dataclasses import dataclass


@dataclass
class User:
    name: str
    status: str
    role: str = "member"


def normalize_name(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


def filter_by_role(users, role):
    return [u for u in users if (u.get("role") if isinstance(u, dict) else u.role) == role]


def count_roles(users):
    counts = {}
    for u in users:
        r = u.get("role") if isinstance(u, dict) else u.role
        counts[r] = counts.get(r, 0) + 1
    return counts


def active_names(users):
    out = []
    for u in users:
        st = u.get("status") if isinstance(u, dict) else u.status
        nm = u.get("name") if isinstance(u, dict) else u.name
        if st == "active":
            out.append(normalize_name(nm))
    return out


def get_status_counts(users):
    counts = {}
    for u in users:
        st = u.get("status") if isinstance(u, dict) else u.status
        counts[st] = counts.get(st, 0) + 1
    return counts


def sort_by_name(users):
    return sorted(users, key=lambda u: u.get("name") if isinstance(u, dict) else u.name)


def batch_filter(users, allowed_roles):
    return [u for u in users if (u.get("role") if isinstance(u, dict) else u.role) in allowed_roles]


def create_user_batch(names, default_role="member"):
    return [User(name=n, status="inactive", role=default_role) for n in names]


def set_all_status(users, new_status):
    for u in users:
        if isinstance(u, dict):
            u["status"] = new_status
        else:
            u.status = new_status


def find_by_name(users, name):
    for u in users:
        nm = u.get("name") if isinstance(u, dict) else u.name
        if normalize_name(nm) == normalize_name(name):
            return u
    return None


def unique_roles(users):
    roles = set()
    for u in users:
        r = u.get("role") if isinstance(u, dict) else u.role
        roles.add(r)
    return sorted(roles)


def user_to_dict(u):
    if isinstance(u, dict):
        return u
    return {"name": u.name, "status": u.status, "role": u.role}


def dict_to_user(d):
    return User(name=d["name"], status=d["status"], role=d.get("role", "member"))


def merge_user_data(base, updates):
    merged = {}
    for u in base:
        nm = u.get("name") if isinstance(u, dict) else u.name
        merged[nm] = u
    for u in updates:
        nm = u.get("name") if isinstance(u, dict) else u.name
        merged[nm] = u
    return list(merged.values())


def active_by_role(users):
    result = {}
    active_only = [u for u in users if (u.get("status") if isinstance(u, dict) else u.status) == "active"]
    for u in active_only:
        r = u.get("role") if isinstance(u, dict) else u.role
        result.setdefault(r, []).append(u)
    return result


def user_summary(users):
    return {
        "total": len(users),
        "active": sum(1 for u in users if (u.get("status") if isinstance(u, dict) else u.status) == "active"),
        "inactive": sum(1 for u in users if (u.get("status") if isinstance(u, dict) else u.status) == "inactive"),
        "roles": unique_roles(users),
    }


def delete_by_name(users, name):
    norm = normalize_name(name)
    return [u for u in users if normalize_name(u.get("name") if isinstance(u, dict) else u.name) != norm]


def promote_to_admin(users, name):
    for u in users:
        nm = u.get("name") if isinstance(u, dict) else u.name
        if normalize_name(nm) == normalize_name(name):
            if isinstance(u, dict):
                u["role"] = "admin"
            else:
                u.role = "admin"
            return True
    return False


def search_users(users, query):
    q = query.lower()
    results = []
    for u in users:
        nm = u.get("name") if isinstance(u, dict) else u.name
        rl = u.get("role") if isinstance(u, dict) else u.role
        if q in nm.lower() or q in rl.lower():
            results.append(u)
    return results


def validate_user_data(users):
    errors = []
    for i, u in enumerate(users):
        if isinstance(u, dict):
            for key in ("name", "status", "role"):
                if key not in u:
                    errors.append(f"user[{i}]: missing key {key}")
            if u.get("status") not in ("active", "inactive"):
                errors.append(f"user[{i}]: invalid status {u.get('status')}")
        else:
            if not hasattr(u, "name"):
                errors.append(f"user[{i}]: missing name")
            if getattr(u, "status", None) not in ("active", "inactive"):
                errors.append(f"user[{i}]: invalid status")
    return errors


def export_csv(users):
    lines = ["name,status,role"]
    for u in users:
        if isinstance(u, dict):
            lines.append(f"{u['name']},{u['status']},{u.get('role','member')}")
        else:
            lines.append(f"{u.name},{u.status},{u.role}")
    return "\n".join(lines)


def import_csv(text):
    users = []
    for line in text.strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            users.append(User(name=parts[0], status=parts[1], role=parts[2] if len(parts) > 2 else "member"))
    return users
