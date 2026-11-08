from PIL import Image

from undo.redact import Redactor, blur_boxes, is_sensitive


def test_sensitive_patterns():
    assert is_sensitive("Carte 4111 1111 1111 1111")
    assert is_sensitive("IBAN FR76 3000 6000 0112 3456 7890 189")
    assert not is_sensitive("Dupont Marie 14/03/1988")
    assert not is_sensitive("12 rue des Lilas, 75011 Paris")


def test_redactor_blurs_only_sensitive_lines():
    img = Image.new("RGB", (200, 100), "white")
    for x in range(0, 200, 2):
        img.putpixel((x, 20), (0, 0, 0))

    class FakeOCR:
        def boxes(self, image):
            return [("4111 1111 1111 1111", (0, 10, 200, 30)), ("Dupont", (0, 60, 100, 80))]

    out = Redactor(FakeOCR())(img)
    assert out.getpixel((0, 20)) != (0, 0, 0)
    assert blur_boxes(img, []) is img
