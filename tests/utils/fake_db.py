from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument


class FakeInsertOneResult:
    def __init__(self, inserted_id: Any | None = None) -> None:
        self.inserted_id = inserted_id


class FakeUpdateResult:
    def __init__(self, matched: int = 0, modified: int = 0) -> None:
        self.matched_count = matched
        self.modified_count = modified


def _apply_projection(doc: Dict[str, Any], projection: Optional[Dict[str, int]]) -> Dict[str, Any]:
    if not projection:
        return deepcopy(doc)
    res = deepcopy(doc)
    # Only support exclusions (0) used by our code
    for k, v in projection.items():
        if v == 0 and k in res:
            res.pop(k, None)
    # Always remove _id when projection specifies {"_id": 0}
    if projection.get("_id") == 0 and "_id" in res:
        res.pop("_id", None)
    return res


def _match_condition(value: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        if "$lt" in cond:
            return value is not None and value < cond["$lt"]
        if "$lte" in cond:
            return value is not None and value <= cond["$lte"]
        if "$gte" in cond:
            return value is not None and value >= cond["$gte"]
        if "$regex" in cond:
            flags = 0
            if cond.get("$options") == "i":
                flags = re.IGNORECASE
            return re.match(cond["$regex"], str(value or ""), flags) is not None
        return False
    else:
        return value == cond


def _matches_filter(doc: Dict[str, Any], flt: Dict[str, Any]) -> bool:
    if not flt:
        return True
    if "$or" in flt:
        return any(_matches_filter(doc, sub) for sub in flt["$or"]) and all(
            _matches_filter(doc, {k: v}) for k, v in flt.items() if k != "$or"
        )
    for k, v in flt.items():
        if not _match_condition(doc.get(k), v):
            return False
    return True


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]], projection: Optional[Dict[str, int]] = None) -> None:
        self._docs = docs
        self._projection = projection
        self._skip = 0
        self._limit = None
        self._sort_field = None
        self._sort_dir = 1

    def sort(self, field: str, direction: int) -> "FakeCursor":
        self._sort_field = field
        self._sort_dir = direction
        return self

    def skip(self, n: int) -> "FakeCursor":
        self._skip = n
        return self

    def limit(self, n: int) -> "FakeCursor":
        self._limit = n
        return self

    def _iter(self) -> Iterable[Dict[str, Any]]:
        items = list(self._docs)
        if self._sort_field:
            items.sort(key=lambda d: (d.get(self._sort_field),), reverse=self._sort_dir == -1)
        if self._skip:
            items = items[self._skip :]
        if self._limit is not None:
            items = items[: self._limit]
        for d in items:
            yield _apply_projection(d, self._projection)

    def __aiter__(self):
        self._iter_it = iter(self._iter())
        return self

    async def __anext__(self):
        try:
            return next(self._iter_it)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self) -> None:
        self._docs: List[Dict[str, Any]] = []
        self._next_id: int = 1

    async def insert_one(self, doc: Dict[str, Any]) -> FakeInsertOneResult:
        # uniqueness: upc and source_url and _id for locks
        key_fields = ["_id", "upc", "source_url"]
        for d in self._docs:
            if any(k in doc and k in d and doc[k] == d[k] for k in key_fields):
                raise DuplicateKeyError("duplicate key")
        # assign a synthetic _id if missing to simulate MongoDB default ObjectId
        if "_id" not in doc:
            doc["_id"] = self._next_id
            self._next_id += 1
        self._docs.append(deepcopy(doc))
        return FakeInsertOneResult()

    async def find_one(self, flt: Dict[str, Any], projection: Optional[Dict[str, int]] = None) -> Optional[Dict[str, Any]]:
        for d in self._docs:
            if _matches_filter(d, flt):
                return _apply_projection(d, projection)
        return None

    def find(self, flt: Dict[str, Any], projection: Optional[Dict[str, int]] = None) -> FakeCursor:
        matches = [deepcopy(d) for d in self._docs if _matches_filter(d, flt)]
        return FakeCursor(matches, projection)

    async def update_one(self, flt: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> FakeUpdateResult:
        for d in self._docs:
            if _matches_filter(d, flt):
                if "$set" in update:
                    d.update(deepcopy(update["$set"]))
                if "$unset" in update:
                    for k in update["$unset"].keys():
                        d.pop(k, None)
                return FakeUpdateResult(matched=1, modified=1)
        if upsert:
            new_doc = deepcopy(update.get("$set", {}))
            new_doc.update({k: v for k, v in flt.items() if not k.startswith("$")})
            await self.insert_one(new_doc)
            return FakeUpdateResult(matched=1, modified=1)
        return FakeUpdateResult(matched=0, modified=0)

    async def find_one_and_update(
        self,
        flt: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        return_document: ReturnDocument = ReturnDocument.AFTER,
    ) -> Optional[Dict[str, Any]]:
        for d in self._docs:
            if _matches_filter(d, flt):
                if "$set" in update:
                    d.update(deepcopy(update["$set"]))
                if return_document == ReturnDocument.AFTER:
                    return deepcopy(d)
                else:
                    return deepcopy(d)
        if upsert:
            new_doc = deepcopy(update.get("$set", {}))
            new_doc.update({k: v for k, v in flt.items() if not k.startswith("$")})
            if any("_id" in doc and doc["_id"] == new_doc.get("_id") for doc in self._docs):
                raise DuplicateKeyError("duplicate key")
            await self.insert_one(new_doc)
            return deepcopy(new_doc)
        return None

    async def count_documents(self, flt: Dict[str, Any]) -> int:
        return sum(1 for d in self._docs if _matches_filter(d, flt))

    async def create_index(self, *args, **kwargs) -> None:
        return None

    async def update_many(self, *args, **kwargs) -> None:
        return None


class FakeDB:
    def __init__(self) -> None:
        self._collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]
