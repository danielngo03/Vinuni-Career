"""Integration tests for the read-only Vietnamese location reference data.

Covers: GET /locations/provinces and GET /locations/provinces/{code}/wards
(called directly as no-auth async functions, matching the router contract),
empty-state when no seed data is loaded, and unknown-province lookup.
"""

from __future__ import annotations

from app.modules.locations.api.router import list_province_wards, list_provinces
from app.shared.location_models import Province, Ward


async def _seed_province(
    db_session, *, code: str = "01", name: str = "Hà Nội", is_central: bool = True
) -> Province:
    province = Province(
        code=code,
        name=name,
        full_name=f"Thành phố {name}",
        slug=name.lower().replace(" ", "-"),
        type="city",
        is_central=is_central,
    )
    db_session.add(province)
    await db_session.flush()
    return province


async def _seed_ward(
    db_session, *, code: str, province_code: str, name: str = "Phường Ba Đình"
) -> Ward:
    ward = Ward(
        code=code,
        name=name,
        full_name=name,
        slug=name.lower().replace(" ", "-"),
        type="ward",
        province_code=province_code,
    )
    db_session.add(ward)
    await db_session.flush()
    return ward


# --------------------------------------------------------------------------- #
# provinces                                                                    #
# --------------------------------------------------------------------------- #


async def test_list_provinces_empty_when_no_seed_data(db_session) -> None:
    result = await list_provinces(session=db_session)
    assert result == {"items": []}


async def test_list_provinces_returns_seeded_rows(db_session) -> None:
    await _seed_province(db_session, code="01", name="Hà Nội")
    await _seed_province(db_session, code="79", name="TP. Hồ Chí Minh", is_central=True)

    result = await list_provinces(session=db_session)
    names = {p["name"] for p in result["items"]}
    assert "Hà Nội" in names
    assert "TP. Hồ Chí Minh" in names
    for p in result["items"]:
        assert set(p.keys()) == {"code", "name", "full_name", "slug", "type", "is_central"}


# --------------------------------------------------------------------------- #
# wards                                                                        #
# --------------------------------------------------------------------------- #


async def test_list_province_wards_returns_wards_for_code(db_session) -> None:
    province = await _seed_province(db_session, code="01", name="Hà Nội")
    await _seed_ward(db_session, code="00001", province_code=province.code, name="Phường Ba Đình")
    await _seed_ward(db_session, code="00004", province_code=province.code, name="Phường Hoàn Kiếm")

    result = await list_province_wards(code=province.code, session=db_session)
    names = {w["name"] for w in result["items"]}
    assert names == {"Phường Ba Đình", "Phường Hoàn Kiếm"}


async def test_list_province_wards_unknown_code_returns_empty(db_session) -> None:
    result = await list_province_wards(code="99", session=db_session)
    assert result == {"items": []}


async def test_list_province_wards_excludes_other_provinces(db_session) -> None:
    hanoi = await _seed_province(db_session, code="01", name="Hà Nội")
    hcmc = await _seed_province(db_session, code="79", name="TP. Hồ Chí Minh")
    await _seed_ward(db_session, code="00001", province_code=hanoi.code, name="Phường Ba Đình")
    await _seed_ward(db_session, code="27000", province_code=hcmc.code, name="Phường Bến Nghé")

    result = await list_province_wards(code=hanoi.code, session=db_session)
    names = {w["name"] for w in result["items"]}
    assert names == {"Phường Ba Đình"}
