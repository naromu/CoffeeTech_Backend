class User:
    def __init__(self, name: str, email: str, password_hash: str, verification_token: str):
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.verification_token = verification_token

    def save(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO "user" (name, email, password_hash, verification_token)
                VALUES (%s, %s, %s, %s)
                RETURNING user_id;
            """, (self.name, self.email, self.password_hash, self.verification_token))
            user_id = cursor.fetchone()[0]
            conn.commit()
            return user_id
