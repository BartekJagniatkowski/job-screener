"""
CLI tool to delete a user account and all associated data.

Usage:
    uv run python delete_user.py <username>
"""
import sys

import database


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: uv run python delete_user.py <username>")
        sys.exit(1)

    username = sys.argv[1].lower().strip()
    user = database.get_user(username)
    if user is None:
        print(f"No account found for '{username}'.")
        sys.exit(1)

    with database.get_conn() as conn:
        job_count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE user_id=?", (user["id"],)
        ).fetchone()[0]
        analysis_count = conn.execute(
            "SELECT COUNT(*) FROM analyses WHERE user_id=?", (user["id"],)
        ).fetchone()[0]

    print(f"Account: {username} (id={user['id']})")
    print(f"  jobs: {job_count}")
    print(f"  analyses: {analysis_count}")
    confirm = input("Delete this account and all associated data? Type the username to confirm: ")
    if confirm.strip().lower() != username:
        print("Aborted — confirmation did not match.")
        sys.exit(1)

    database.delete_user(username)
    print(f"Account '{username}' deleted.")


if __name__ == "__main__":
    main()
