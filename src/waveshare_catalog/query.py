"""Filter the local catalogue. No network, so it is cheap to iterate on."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Filter:
    """The conditions a product must satisfy. Unset fields are ignored."""

    name: str | None = None
    part_no: str | None = None
    category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    has_options: bool | None = None
    detailed: bool | None = None
    listed: bool | None = None
    limit: int | None = None


def search(connection: sqlite3.Connection, criteria: Filter) -> list[sqlite3.Row]:
    """Products matching `criteria`, cheapest first."""
    where: list[str] = []
    params: list[object] = []

    if criteria.name:
        where.append("p.name LIKE ?")
        params.append(f"%{criteria.name}%")
    if criteria.part_no:
        where.append("p.part_no LIKE ?")
        params.append(f"%{criteria.part_no}%")
    if criteria.category:
        where.append(
            "EXISTS (SELECT 1 FROM product_categories pc WHERE pc.product_url = p.url "
            "AND pc.category_url LIKE ?)"
        )
        params.append(f"%{criteria.category}%")
    if criteria.price_min is not None:
        where.append("p.price_min >= ?")
        params.append(criteria.price_min)
    if criteria.price_max is not None:
        where.append("p.price_min <= ?")
        params.append(criteria.price_max)
    if criteria.has_options is not None:
        where.append("p.has_options = ?")
        params.append(int(criteria.has_options))
    if criteria.listed is not None:
        where.append(
            "p.name IS NOT NULL AND p.name != ''"
            if criteria.listed
            else "(p.name IS NULL OR p.name = '')"
        )
    if criteria.detailed is not None:
        clause = "EXISTS" if criteria.detailed else "NOT EXISTS"
        where.append(f"{clause} (SELECT 1 FROM details d WHERE d.product_url = p.url)")

    sql = "SELECT p.* FROM products p"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.price_min IS NULL, p.price_min, p.name"
    if criteria.limit is not None:
        sql += " LIMIT ?"
        params.append(criteria.limit)
    return list(connection.execute(sql, params))
