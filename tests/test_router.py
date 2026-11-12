from romeo.agent.router import route


def test_simple_goes_local():
    assert route("วันนี้วันอะไร").engine == "ollama"


def test_screen_goes_cloud():
    assert route("คลิกปุ่ม Save ให้หน่อย").engine == "cloud"


def test_phone_goes_cloud():
    assert route("ส่งข้อความหาแม่บอกว่าถึงบ้านแล้ว").engine == "cloud"


def test_multi_step_goes_cloud():
    assert route("open notepad then write a poem and then save it").engine == "cloud"
