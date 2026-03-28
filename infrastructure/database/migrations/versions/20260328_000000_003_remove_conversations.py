"""remove conversations table

Revision ID: 003_remove_conversations
Revises: 002_bot_messages
Create Date: 2026-03-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_remove_conversations"
down_revision: Union[str, None] = "002_bot_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the index first, then the table
    op.drop_index("idx_conversations_user_timestamp", table_name="conversations")
    op.drop_table("conversations")


def downgrade() -> None:
    # Recreate table if needed for rollback
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_conversations_user_timestamp", "conversations", ["user_id", "timestamp"])
