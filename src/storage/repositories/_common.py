from __future__ import annotations


def get_row_by_identifier(
    connection,
    *,
    table_name: str,
    identifier: str,
    order_column: str,
    public_id_column: str = "public_id",
):
    row = connection.execute(
        f"SELECT * FROM {table_name} WHERE {public_id_column} = ?",
        (identifier,),
    ).fetchone()
    if row is not None:
        return row

    row = connection.execute(
        f"SELECT * FROM {table_name} WHERE id = ?",
        (identifier,),
    ).fetchone()
    if row is not None:
        return row

    prefix_rows = connection.execute(
        f"SELECT * FROM {table_name} WHERE id LIKE ? ORDER BY {order_column} DESC LIMIT 2",
        (f"{identifier}%",),
    ).fetchall()
    if len(prefix_rows) == 1:
        return prefix_rows[0]
    return None


def allocate_public_id(connection, *, table_name: str, prefix: str) -> str:
    row = connection.execute(
        f"""
        SELECT public_id
        FROM {table_name}
        WHERE public_id LIKE ?
        ORDER BY CAST(SUBSTR(public_id, 2) AS INTEGER) DESC
        LIMIT 1
        """,
        (f"{prefix}%",),
    ).fetchone()
    next_number = 1
    if row is not None and row["public_id"]:
        try:
            next_number = int(str(row["public_id"])[1:]) + 1
        except ValueError:
            next_number = 1
    return f"{prefix}{next_number:04d}"
