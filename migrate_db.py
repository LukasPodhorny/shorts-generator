import sqlite3
import os

# Path to your database file
DB_FILE = "database.db"

if not os.path.exists(DB_FILE):
    print(f"Database file {DB_FILE} not found. Nothing to migrate.")
    exit()

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

new_columns = [
    ("stripe_customer_id", "TEXT"),
    ("stripe_subscription_id", "TEXT"),
    ("subscription_status", "TEXT"),
    ("plan_id", "TEXT"),
    ("current_period_end", "TIMESTAMP"),
]

print("Starting migration...")

for col_name, col_type in new_columns:
    try:
        cursor.execute(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}")
        print(f"✅ Added column: {col_name}")
    except sqlite3.OperationalError as e:
        print(f"⚠️  Skipped {col_name}: {e}")

# Create indexes for the new fields
indexes = ["stripe_customer_id", "stripe_subscription_id"]
for idx in indexes:
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS ix_user_{idx} ON user ({idx})")
        print(f"✅ Created index for: {idx}")
    except sqlite3.OperationalError as e:
        print(f"⚠️  Skipped index for {idx}: {e}")

# Create SubscriptionPlan table if it doesn't exist
try:
    cursor.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='subscriptionplan'"
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            """
            CREATE TABLE subscriptionplan (
                stripe_price_id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                credits INTEGER NOT NULL,
                description TEXT
            )
        """
        )
        print("✅ Created table: subscriptionplan")
        # Seed the initial plan from your code
        cursor.execute(
            "INSERT INTO subscriptionplan (stripe_price_id, name, credits) VALUES ('price_1T5OcYRdD1Zd1schrm7HhMq7', 'Pro Plan', 200)"
        )
        print("✅ Seeded default plan data")
except Exception as e:
    print(f"⚠️  Error creating subscriptionplan table: {e}")

conn.commit()
conn.close()
print("🚀 Migration complete. You can now restart your server.")
