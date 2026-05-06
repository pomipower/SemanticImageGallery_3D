"""add_embedding_status_and_fts5

Revision ID: a03a176b3d88
Revises: 522e7193f7f6
Create Date: 2026-05-05 13:16:00.881323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a03a176b3d88'
down_revision: Union[str, None] = '522e7193f7f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add embedding_status column
    with op.batch_alter_table('images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embedding_status', sa.String(length=20), nullable=False, server_default='pending'))

    # Create FTS5 virtual table for keyword search
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS images_fts USING fts5(
            filename,
            caption,
            tags,
            ocr_text,
            content='',
            tokenize='porter ascii'
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS images_fts")
    with op.batch_alter_table('images', schema=None) as batch_op:
        batch_op.drop_column('embedding_status')
