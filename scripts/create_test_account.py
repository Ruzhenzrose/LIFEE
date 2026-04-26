"""建一个测试账号（email_verified=1，自定义 credits）。
用法：
    # 直接在生产服务器上跑
    python scripts/create_test_account.py teammate@example.com mypassword 9999

    # 或本地 admin 通过 SSH 在 prod 上执行
    scp scripts/create_test_account.py root@47.83.184.82:/tmp/
    ssh root@47.83.184.82 "cd /opt/lifee && python /tmp/create_test_account.py teammate@example.com mypassword 9999"

跑完后，队友本地下次 start-lifee.bat 会把这个号同步到本地 data/lifee.db，
两边都能用同一套 email+password 登录。
"""
import sys
from lifee import store, auth


def main():
    if len(sys.argv) < 3:
        print("usage: python create_test_account.py <email> <password> [credits=9999]")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    password = sys.argv[2]
    credits = int(sys.argv[3]) if len(sys.argv) > 3 else 9999

    existing = store.user_by_email(email)
    if existing:
        uid = existing["id"]
        store.user_set_password(uid, auth.hash_password(password))
        store.user_set_verified(uid)
        print(f"[update] {email} already exists, password reset; id={uid}")
    else:
        uid = store.user_create(email, auth.hash_password(password))
        store.user_set_verified(uid)
        print(f"[create] {email}; id={uid}")

    store.credits_set(uid, credits)
    print(f"[credits] {email}: balance={credits}")


if __name__ == "__main__":
    main()
