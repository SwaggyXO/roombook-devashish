def test_list_rooms(client):
    res = client.get("/rooms")
    assert res.status_code == 200
    assert [r["name"] for r in res.json()] == ["Focus Room", "Board Room", "Huddle"]


def test_list_rooms_without_user_has_no_bookable_field(client):
    assert all("bookable" not in room for room in client.get("/rooms").json())


def test_list_rooms_for_an_intern_marks_the_board_room_unbookable(client):
    res = client.get("/rooms", params={"user_id": 4})
    assert res.status_code == 200
    assert {r["name"]: r["bookable"] for r in res.json()} == {
        "Focus Room": True,
        "Board Room": False,
        "Huddle": True,
    }


def test_list_rooms_for_a_manager_marks_every_room_bookable(client):
    res = client.get("/rooms", params={"user_id": 3})
    assert [r["bookable"] for r in res.json()] == [True, True, True]


def test_list_rooms_keeps_the_room_fields_when_a_user_is_given(client):
    res = client.get("/rooms", params={"user_id": 3})
    assert res.json()[0] == {"id": 1, "name": "Focus Room", "capacity": 4, "bookable": True}


def test_list_rooms_for_an_unknown_user(client):
    assert client.get("/rooms", params={"user_id": 42}).status_code == 404


def test_create_room(client):
    res = client.post("/rooms", json={"name": "Phone Booth", "capacity": 1})
    assert res.status_code == 201
    assert res.json()["name"] == "Phone Booth"


def test_create_room_duplicate_name(client):
    res = client.post("/rooms", json={"name": "Huddle", "capacity": 3})
    assert res.status_code == 409


def test_list_users(client):
    res = client.get("/users")
    assert res.status_code == 200
    roles = {u["name"]: u["role"] for u in res.json()}
    assert roles["Divya"] == "intern"
    assert roles["Chen"] == "manager"
